#!/usr/bin/env python3
"""Apply the contamination detector retroactively to stored per-attempt events.

Usage::

    $PY evals/harness/rescore_contamination.py \\
        evals/airflow/results/baseline-2026-09-30 evals/airflow/results/baseline-run3-2026-09-30 \\
        evals/airflow/results/skill-2026-09-30 --out evals/airflow/results/altimate-code-2026-09-30-summary

For campaigns run before ``isolation.scan_contamination`` existed. Each attempt's
``events.jsonl`` (git-ignored, so only where it is still on disk) is scanned with
the same forbidden roots ``run_eval.IsolationRoots`` uses today, rebuilt for that
campaign:

- the attempt's scratch dir is not recorded in old campaigns. It is inferred from
  the events: the most referenced ``<work root>/<campaign dir>/<case>-<suffix>``
  directory. Staged skills are ``<campaign dir>/skills``. Both are allowed.
- campaigns whose ``meta.json`` has no ``agent_envs`` ran the agent in the grader
  venv. There it was the agent's own activated venv, so the ``grader-env`` root is
  not forbidden for them (references are counted as ``grader_env_refs``).

Each hit carries evidence (heuristic, for triage; the flag itself is the
detector's): ``first_access`` (``overwrite`` when this attempt's first use of the
path replaces it, ``generated`` for per-process names such as ``/tmp/x_$$``,
``own_scratch_mistyped`` for a garbled path to its own scratch dir, else ``use``),
``prior_users`` (other attempts, from every result dir with stored events, that
referenced the same path earlier) and ``concurrent_writers`` (other attempts that
replaced the path between this attempt's first and last use of it). A hit is
``strong`` when it is a ``use`` of a root outside shared temp (repo, results,
other attempts, user skills, host data) or of a shared-temp path another attempt
used earlier, or an ``overwrite`` that a concurrent writer may have replaced
before this attempt read it back; otherwise ``weak``.

Outputs in ``--out``: ``contamination.jsonl`` (one row per attempt),
``all/`` and ``excluding-flagged/`` (``report.py`` results.json + REPORT.md; a run
is dropped when its scored attempt is flagged), ``excluding-strong/`` (drops only
strong-evidence runs, a sensitivity check), ``meta.json``, and ``REPORT.md`` +
``results.json`` (flag counts, pass-rate tables with all runs and without flagged
runs, per-case paired deltas, pooled deltas with case-clustered CIs, and a check of
whether each delta's sign or significance changes when flagged runs are dropped).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS_DIR))
import grading as g  # noqa: E402
import isolation as iso  # noqa: E402
import report as rp  # noqa: E402
import run_eval as re_  # noqa: E402
import sanitize as san  # noqa: E402

STRONG_ROOTS = ("repo", "results", "work-root", "user-skills", "altimate-data", "user-config", "grader-env")
_WRITE_TOOLS = ("write",)


def tool_calls_with_time(events: list[dict]) -> list[dict]:
    """``grading.tool_uses`` rows plus each call's event ``timestamp`` (ms, may be None)."""
    uses = g.tool_uses(events)
    if g.is_claude_stream(events):
        return [dict(u, ts=None) for u in uses]
    stamps = [e.get("timestamp") for e in events if e.get("type") == "tool_use"]
    return [dict(u, ts=stamps[i] if i < len(stamps) else None) for i, u in enumerate(uses)]


def infer_scratch(calls: list[dict], work_root: str, case: str, home: str) -> tuple[str | None, str | None]:
    """(attempt scratch dir, campaign work dir) inferred from paths under ``work_root``."""
    rx = re.compile(re.escape(path_key(work_root, home).rstrip("/")) + r"/([^/]+)/(" + re.escape(case) + r"-[^/]+)")
    seen: Counter = Counter()
    for u in calls:
        for p in iso._input_paths(str(u.get("tool") or ""), u.get("input") or {}):
            m = rx.match(path_key(p, home))
            if m:
                seen[(m.group(1), m.group(2))] += 1
    if not seen:
        return None, None
    (campaign, scratch), _ = seen.most_common(1)[0]
    base = os.path.join(work_root, campaign)
    return os.path.join(base, scratch), base


def build_policy(scratch: str | None, campaign_dir: str | None, out_dir: Path, work_root: str,
                 grader_env_is_agent_env: bool, home: str) -> iso.ContaminationPolicy:
    roots = re_.IsolationRoots(scratch=Path(scratch or "/nonexistent-scratch"), agent_venv=Path("/nonexistent-venv"),
                               staged_skills=Path(os.path.join(campaign_dir, "skills") if campaign_dir
                                                  else "/nonexistent-skills"),
                               out_dir=out_dir.resolve(), work_root=Path(work_root), base={"HOME": home})
    forbidden = [(lab, p) for lab, p in roots.forbidden() if not (grader_env_is_agent_env and lab == "grader-env")]
    allowed = [a for a in roots.allowed() if not a.startswith("/nonexistent")]
    return iso.ContaminationPolicy(forbidden, allowed, home)


def _overwrites(call: dict, path: str) -> bool:
    """True if ``call`` replaces ``path`` (write tool, ``>`` redirect, ``rm -rf``, ``cp``/``mv`` target, ``tee``)."""
    tool = str(call.get("tool") or "")
    inp = call.get("input") or {}
    if tool in _WRITE_TOOLS:
        return any(inp.get(k) == path for k in ("filePath", "file_path", "path"))
    if tool != "bash":
        return False
    cmd = str(inp.get("command") or "")
    p = re.escape(path)
    end = r"(?=$|[\s;&|)'\"`])"
    first_ref = re.search(rf"{p}{end}", cmd)
    if not first_ref:
        return False
    # Only an overwrite that is the command's first reference to the path counts:
    # `cat /tmp/x; echo y > /tmp/x` reads the old content first.
    for rx in (rf"(?<![>&0-9])>\s*['\"]?({p}){end}", rf"\brm\s+-\w*[rf]\w*\s+(?:[^;&|]*\s)?['\"]?({p}){end}",
               rf"\btee\s+(?!-a)['\"]?({p}){end}", rf"\b(?:cp|mv)\s+(?:-\w+\s+)*\S+\s+['\"]?({p})['\"]?\s*(?:$|[;&|])"):
        m = re.search(rx, cmd)
        if m and m.start(1) == first_ref.start():
            return True
    return False


def _generated(call: dict, path: str) -> bool:
    """True if ``path`` is a prefix completed per process (``/tmp/x_$$``, ``mktemp /tmp/x.XXXXXX``)."""
    if re.search(r"X{3,}$", path):
        return True
    text = json.dumps(call.get("input") or {})
    return bool(re.search(re.escape(path) + r"\$", text))


def path_key(path: str, home: str) -> str:
    p = iso._norm(path, home)
    for a, b in (("/private/tmp", "/tmp"), ("/private/var", "/var")):
        if p == a or p.startswith(a + "/"):
            p = b + p[len(a):]
    return p


def scan_attempt(events: list[dict], case: str, out_dir: Path, work_root: str, grader_env_is_agent_env: bool,
                 home: str) -> dict:
    calls = tool_calls_with_time(events)
    scratch, campaign = infer_scratch(calls, work_root, case, home)
    policy = build_policy(scratch, campaign, out_dir, work_root, grader_env_is_agent_env, home)
    # Scan call by call: scan_contamination keeps only its first 50 hits per call list.
    res = {"contamination_suspect": False, "hits": [], "denied_hits": []}
    for i, u in enumerate(calls):
        one = iso.scan_contamination([u], policy)
        res["contamination_suspect"] |= one["contamination_suspect"]
        res["hits"] += [dict(h, call=i) for h in one["hits"]]
        res["denied_hits"] += [dict(h, call=i) for h in one["denied_hits"]]
    grader_refs = 0
    if grader_env_is_agent_env:
        genv = [str(d) for d in re_.grader_env_dirs()]
        grader_refs = sum(1 for u in calls for p in iso._input_paths(str(u.get("tool") or ""), u.get("input") or {})
                          if any(iso._under(iso._norm(p, home), d) for d in genv))
    first: dict[str, dict] = {}
    for h in res["hits"]:
        first.setdefault(path_key(h["path"], home), h)
    own = os.path.basename(scratch) if scratch else None
    own_suffix = "-" + own[len(case) + 1:] if own else None
    for h in res["hits"]:
        k = path_key(h["path"], home)
        if h["root"] == "work-root" and own and any(c == own or c.endswith(own_suffix) for c in h["path"].split("/")):
            h["first_access"] = "own_scratch_mistyped"
        elif _generated(calls[h["call"]], h["path"]):
            h["first_access"] = "generated"
        else:
            f = first[k]
            h["first_access"] = "overwrite" if _overwrites(calls[f["call"]], f["path"]) else "use"
        h["ts"] = calls[h["call"]].get("ts")
        h["key"] = k
    return {"scratch": scratch, "campaign_work_dir": campaign, "n_tool_calls": len(calls),
            "grader_env_refs": grader_refs, "start_ts": next((c["ts"] for c in calls if c.get("ts")), None), **res}


def path_index(result_dirs: list[Path], home: str) -> dict[str, list[tuple[int, str, tuple[int, ...]]]]:
    """{normalized shared-temp path: [(first ts, attempt id, write timestamps)]} over every stored attempt.

    Write timestamps are tool calls that replace the path (see :func:`_overwrites`).
    """
    idx: dict[str, dict[str, list]] = defaultdict(dict)
    for d in result_dirs:
        for ev in sorted(d.glob("runs/*/*/*/attempt-*/events.jsonl")):
            aid = str(ev.parent.relative_to(d.parent))
            for u in tool_calls_with_time(g.load_events(ev)):
                ts = u.get("ts")
                if ts is None:
                    continue
                for p in iso._input_paths(str(u.get("tool") or ""), u.get("input") or {}):
                    k = path_key(p, home)
                    if not k.startswith(("/tmp/", "/var/tmp/", "/var/folders/")):
                        continue
                    ent = idx[k].setdefault(aid, [ts, []])
                    ent[0] = min(ent[0], ts)
                    if _overwrites(u, p):
                        ent[1].append(ts)
    return {k: sorted((e[0], a, tuple(sorted(e[1]))) for a, e in v.items()) for k, v in idx.items()}


def classify(scan: dict, index: dict, self_id: str) -> str:
    """``strong``, ``weak`` or ``none`` for one attempt's scan.

    Adds ``prior_users`` (other attempts that used the path before this hit) and
    ``concurrent_writers`` (other attempts that replaced the path between this
    attempt's first and last use of it, so a file it wrote may have been swapped
    before it read it back).
    """
    level = "none"
    window: dict[str, list[int]] = {}
    for h in scan["hits"]:
        if h.get("ts") is not None:
            w = window.setdefault(h["key"], [h["ts"], h["ts"]])
            w[0], w[1] = min(w[0], h["ts"]), max(w[1], h["ts"])
    for h in scan["hits"]:
        users = [(f, a, writes) for f, a, writes in index.get(h["key"], []) if a != self_id]
        prior = [a for f, a, _w in users if h.get("ts") is not None and f < h["ts"]]
        w = window.get(h["key"])
        concurrent = [a for _f, a, writes in users if w and any(w[0] < t < w[1] for t in writes)]
        h["prior_users"], h["n_prior_users"] = prior[:5], len(prior)
        h["concurrent_writers"] = concurrent[:5]
        if h["first_access"] in ("generated", "own_scratch_mistyped"):
            strong = False
        elif h["first_access"] == "overwrite":
            strong = h["root"] == "shared-temp" and bool(concurrent)
        else:
            strong = h["root"] in STRONG_ROOTS or (h["root"] == "shared-temp" and bool(prior))
        h["strength"] = "strong" if strong else "weak"
        level = "strong" if strong else ("weak" if level == "none" else level)
    return level


def attempt_dir(result_dir: Path, row: dict, attempt: dict) -> Path:
    return (result_dir / "runs" / row["case"] / re_.slug(row["model"]) / f"run-{row['run']}"
            / f"attempt-{attempt.get('attempt', 0)}")


def rescore(dirs: list[Path], index_dirs: list[Path], work_root: str, home: str) -> tuple[list[dict], list[dict]]:
    """(per-attempt records, report rows with ``contamination_*`` set from the rescan)."""
    rows, _metas = rp.load_rows(dirs)
    raw_meta = {str(d): json.loads((d / "meta.json").read_text()) for d in dirs if (d / "meta.json").exists()}
    index = path_index(index_dirs, home)
    records = []
    for r in rows:
        src = Path(r["_source"])
        grader_is_agent = not (raw_meta.get(str(src)) or {}).get("agent_envs")
        attempts = [a for a in r.get("attempts") or [] if a.get("status") not in rp.SKIPPED]
        flagged_final = strong_final = flagged_any = False
        for i, a in enumerate(attempts):
            adir = attempt_dir(src, r, a)
            ev = adir / "events.jsonl"
            rec = {k: r.get(k) for k in ("case", "split", "area", "arm", "model", "run")} | {
                "source": src.name, "attempt": a.get("attempt", i), "status": a.get("status"),
                "scored": i == len(attempts) - 1, "events_available": ev.exists()}
            if not ev.exists():
                rec.update(contamination_suspect=None, evidence_strength=None)
                records.append(rec)
                continue
            scan = scan_attempt(g.load_events(ev), r["case"], src, work_root, grader_is_agent, home)
            level = classify(scan, index, str(adir.relative_to(src.parent)))
            roots = Counter(h["root"] for h in scan["hits"])
            rec.update(contamination_suspect=scan["contamination_suspect"], evidence_strength=level,
                       hit_roots=dict(roots), n_hits=len(scan["hits"]),
                       scratch_inferred=scan["scratch"] is not None, grader_env_refs=scan["grader_env_refs"],
                       hits=[{k: h.get(k) for k in ("tool", "path", "root", "first_access", "strength",
                                                     "n_prior_users", "prior_users", "concurrent_writers")}
                             for h in scan["hits"][:20]],
                       denied_hits=scan["denied_hits"][:10])
            a["isolation"] = {"hits": [{k: h[k] for k in ("tool", "path", "root")} for h in scan["hits"]],
                              "rescored": True}
            flagged_any = flagged_any or scan["contamination_suspect"]
            if rec["scored"]:
                flagged_final, strong_final = scan["contamination_suspect"], level == "strong"
            records.append(rec)
        r["contamination_suspect"] = flagged_final
        r["contamination_strong"] = strong_final
        r["contamination_any_attempt"] = flagged_any
        r["_rescore_flags"] = (flagged_final, strong_final)
    return records, rows


def dedupe(rows: list[dict]) -> list[dict]:
    """``report.dedupe_runs``, keeping each kept row's own scored-attempt flags.

    ``dedupe_runs`` ORs the flags of a superseded paid row into the row that replaces
    it; exclusion here depends only on the attempt that was scored.
    """
    kept, _dropped = rp.dedupe_runs(rows)
    for r in kept:
        if "_rescore_flags" in r:
            r["contamination_suspect"], r["contamination_strong"] = r["_rescore_flags"]
    return kept


def _counts(records: list[dict]) -> list[dict]:
    out: dict[tuple, Counter] = defaultdict(Counter)
    for x in records:
        if not x["scored"]:
            continue
        c = out[(x["split"], x["arm"], x["model"])]
        c["attempts"] += 1
        c["flagged"] += bool(x.get("contamination_suspect"))
        c["strong"] += x.get("evidence_strength") == "strong"
        c["no_events"] += not x["events_available"]
        if x.get("contamination_suspect") and x["status"] not in rp.INVALID:
            c["flagged_pass" if x["status"] == "ok" else "flagged_fail"] += 1
    return [{"split": s, "arm": a, "model": m, **dict(c)} for (s, a, m), c in sorted(out.items())]


def _pass_table(res: dict) -> list[str]:
    lines = ["| split | model | baseline pass (n) | skill pass (n) | paired delta [95% CI] | cases |",
             "|---|---|---|---|---|---|"]
    by = {(r["split"], r["arm"], r["model"]): r for r in res["by_split_arm_model"]}
    for d in res["paired_deltas"]:
        b, s = by.get((d["split"], "baseline", d["model"])), by.get((d["split"], "skill", d["model"]))

        def cell(x):
            if not x or x["pass_rate"] is None:
                return "-"
            return f"{round(x['pass_rate'] * x['n_valid'])}/{x['n_valid']} ({x['pass_rate'] * 100:.0f}%)"
        lo, hi = d["ci95_delta_pass_rate"]
        lines.append(f"| {d['split']} | {short(d['model'])} | {cell(b)} | {cell(s)} | "
                     f"{d['mean_delta_pass_rate']:+.2f} [{lo:+.2f}, {hi:+.2f}] | {d['n_cases']} |")
    for d in res.get("pooled_deltas") or []:
        lo, hi = d["ci95_delta_pass_rate"]
        lines.append(f"| {d['split']} | pooled ({d['n_pairs']} pairs, CI clustered by case) | | | "
                     f"{d['mean_delta_pass_rate']:+.2f} [{lo:+.2f}, {hi:+.2f}] | {d['n_cases']} |")
    return lines


def short(model: str) -> str:
    m = re.search(r"claude-([a-z]+)-(\d+)-(\d+)", model)
    return f"{m.group(1).capitalize()} {m.group(2)}.{m.group(3)}" if m else model


def render_summary(records: list[dict], reports: dict[str, dict], meta: dict) -> str:
    L = ["# altimate-code campaigns 2026-09-30: retroactive contamination rescore", "",
         "Detector: `isolation.scan_contamination` with today's forbidden roots, rebuilt per campaign "
         "(see `evals/harness/rescore_contamination.py`). Inputs: " + ", ".join(f"`{d}`" for d in meta["inputs"]) + ".",
         "A run is dropped from the excluding tables when its scored attempt is flagged. "
         "Evidence strength is a heuristic: `strong` = the attempt used a shared-temp path another attempt had "
         "used earlier without overwriting it first, used a non-temp forbidden root, or overwrote a shared-temp "
         "path that another attempt also wrote before this attempt's last use of it (a race); `weak` = no sign of "
         "another attempt's state: paths this attempt overwrote first with no concurrent writer (e.g. "
         "`> /tmp/summary.md`), per-process names (`/tmp/x_$$`, `mktemp`), a mistyped path to its own scratch dir, "
         "or shared-temp paths no earlier attempt used. Manual review of the strong hits: `REVIEW.md`.", "",
         "## Flagged scored attempts", "",
         "| split | arm | model | attempts | flagged | strong | flagged & passed | flagged & failed | no events |",
         "|---|---|---|---|---|---|---|---|---|"]
    for c in _counts(records):
        L.append(f"| {c['split']} | {c['arm']} | {short(c['model'])} | {c.get('attempts', 0)} | {c.get('flagged', 0)} | "
                 f"{c.get('strong', 0)} | {c.get('flagged_pass', 0)} | {c.get('flagged_fail', 0)} | "
                 f"{c.get('no_events', 0)} |")
    roots = Counter(k for x in records if x["scored"] for k in (x.get("hit_roots") or {}))
    L += ["", f"Hit roots (scored attempts with at least one hit): {dict(roots)}.", ""]
    strong = [x for x in records if x["scored"] and x.get("evidence_strength") == "strong"]
    if strong:
        L += ["## Strong-evidence attempts", ""]
        for x in strong:
            uniq = {(h["path"], h["root"]): h for h in x["hits"] if h["strength"] == "strong"}
            ev = "; ".join(f"{h['tool']} `{h['path']}` ({h['root']}, first {h['first_access']}, "
                           f"{h['n_prior_users']} earlier user(s), "
                           f"{len(h.get('concurrent_writers') or [])} concurrent writer(s))" for h in uniq.values())
            L.append(f"- {x['split']} {x['arm']} {short(x['model'])} `{x['case']}` run {x['run']} "
                     f"[{x['status']}]: {ev}")
        L.append("")
    nonscored = [x for x in records if not x["scored"] and x.get("contamination_suspect")]
    L += [f"Flagged non-scored (retried infra_error) attempts: {len(nonscored)}.", ""]
    for name, title in (("all", "All runs"), ("excluding-flagged", "Excluding flagged runs"),
                        ("excluding-strong", "Excluding strong-evidence runs only (sensitivity)")):
        L += [f"## Pass rate: {title}", ""] + _pass_table(reports[name]) + [""]
    L += ["Paired delta = mean over cases of (skill - baseline) pass rate, same case and model; 95% CI is a "
          "percentile bootstrap over cases (10,000 resamples, seed 0). Pooled rows average every (case, model) pair "
          "and resample cases with all their models.", ""]
    return "\n".join(L) + "\n"


def per_case_deltas(reports: dict[str, dict]) -> list[dict]:
    """One row per (split, model, case): pass rates and delta in every report variant."""
    out: dict[tuple, dict] = {}
    for name, res in reports.items():
        for d in res["paired_deltas"]:
            for c in d["cases"]:
                row = out.setdefault((d["split"], d["model"], c["case"]),
                                     {"split": d["split"], "model": d["model"], "case": c["case"]})
                row[name] = {k: c[k] for k in ("baseline_pass_rate", "skill_pass_rate", "delta_pass_rate")}
    return [out[k] for k in sorted(out)]


def _significant(ci: list | tuple) -> bool:
    lo, hi = ci
    return lo is not None and (lo > 0 or hi < 0)


def conclusion_check(reports: dict[str, dict], base: str = "all", alt: str = "excluding-flagged") -> list[dict]:
    """Per (split, model) and pooled row: does dropping flagged runs flip the sign or significance?"""
    def rows(res):
        out = {(d["split"], d["model"]): d for d in res["paired_deltas"]}
        out.update({(d["split"], "pooled"): d for d in res.get("pooled_deltas") or []})
        return out
    a, b = rows(reports[base]), rows(reports[alt])
    checks = []
    for key in sorted(a, key=lambda k: (k[0], k[1] == "pooled", k[1])):
        x, y = a[key], b.get(key)
        rec = {"split": key[0], "model": key[1],
               base: {"delta": x["mean_delta_pass_rate"], "ci95": x["ci95_delta_pass_rate"], "n_cases": x["n_cases"]},
               alt: None if y is None else {"delta": y["mean_delta_pass_rate"], "ci95": y["ci95_delta_pass_rate"],
                                            "n_cases": y["n_cases"]}}
        if y is None:
            rec.update(sign_same=None, significance_same=None, changed=True)
        else:
            sign_same = (x["mean_delta_pass_rate"] > 0) == (y["mean_delta_pass_rate"] > 0)
            sig_same = _significant(x["ci95_delta_pass_rate"]) == _significant(y["ci95_delta_pass_rate"])
            rec.update(sign_same=sign_same, significance_same=sig_same, changed=not (sign_same and sig_same))
        checks.append(rec)
    return checks


def _ci(ci) -> str:
    lo, hi = ci
    return "-" if lo is None else f"[{lo:+.2f}, {hi:+.2f}]"


def render_extra(reports: dict[str, dict]) -> list[str]:
    """Per-case paired deltas and the all-vs-excluding-flagged conclusion check."""
    L = ["## Per-case paired deltas (skill - baseline pass rate)", "",
         "`-` = no valid pair left after exclusion.", "",
         "| split | model | case | baseline (all) | skill (all) | delta (all) | delta (excl. flagged) | "
         "delta (excl. strong) |", "|---|---|---|---|---|---|---|---|"]

    def f(x, k):
        return "-" if not x else (f"{x[k]:+.2f}" if k.startswith("delta") else f"{x[k] * 100:.0f}%")
    for r in per_case_deltas(reports):
        a = r.get("all")
        L.append(f"| {r['split']} | {short(r['model'])} | `{r['case']}` | {f(a, 'baseline_pass_rate')} | "
                 f"{f(a, 'skill_pass_rate')} | {f(a, 'delta_pass_rate')} | "
                 f"{f(r.get('excluding-flagged'), 'delta_pass_rate')} | "
                 f"{f(r.get('excluding-strong'), 'delta_pass_rate')} |")
    L += ["", "## Do conclusions change when flagged runs are dropped?", "",
          "Significant = 95% CI excludes 0.", "",
          "| split | model | delta all [CI] | delta excl. flagged [CI] | same sign | same significance |",
          "|---|---|---|---|---|---|"]
    for c in conclusion_check(reports):
        a, b = c["all"], c["excluding-flagged"]
        name = "pooled (clustered by case)" if c["model"] == "pooled" else short(c["model"])
        bcell = "-" if b is None else f"{b['delta']:+.2f} {_ci(b['ci95'])} ({b['n_cases']} cases)"
        yn = {True: "yes", False: "**no**", None: "-"}
        L.append(f"| {c['split']} | {name} | {a['delta']:+.2f} {_ci(a['ci95'])} ({a['n_cases']} cases) | {bcell} | "
                 f"{yn[c['sign_same']]} | {yn[c['significance_same']]} |")
    return L + [""]


def _sha_dir(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in path.rglob("*") if x.is_file() and "__pycache__" not in x.parts):
        h.update(str(p.relative_to(path)).encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", type=Path, help="run_eval.py result dirs to rescore")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--index-dirs", nargs="*", type=Path, default=None,
                    help="result dirs whose stored events count as earlier users of shared paths "
                         "(default: every dir next to the inputs that has runs/)")
    ap.add_argument("--work-root", default=os.environ.get("EVAL_WORK_ROOT", "~/.cache/des-evals/work"))
    ap.add_argument("--bootstrap", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    home = os.path.expanduser("~")
    work_root = os.path.normpath(os.path.expanduser(args.work_root))
    index_dirs = args.index_dirs if args.index_dirs is not None else sorted(
        {p for d in args.dirs for p in d.parent.iterdir() if (p / "runs").is_dir()})
    records, rows = rescore(args.dirs, index_dirs, work_root, home)
    rows = dedupe(rows)
    variants = {"all": rows,
                "excluding-flagged": [r for r in rows if not r.get("contamination_suspect")],
                "excluding-strong": [r for r in rows if not r.get("contamination_strong")]}
    args.out.mkdir(parents=True, exist_ok=True)
    reports = {}
    for name, rs in variants.items():
        res = rp.aggregate(rs, args.bootstrap, args.seed)
        res["sources"] = [{"dir": str(d)} for d in args.dirs]
        res["n_runs"] = len(rs)
        reports[name] = res
        (args.out / name).mkdir(exist_ok=True)
        san.write_json(args.out / name / "results.json", res)
        san.write_text(args.out / name / "REPORT.md", rp.render_markdown(res))
    with (args.out / "contamination.jsonl").open("w") as fh:
        for x in records:
            fh.write(san.dumps(x, indent=None) + "\n")
    meta = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "inputs": [str(d) for d in args.dirs], "index_dirs": [str(d) for d in index_dirs],
            "work_root": work_root, "harness_sha256": _sha_dir(HARNESS_DIR),
            "current_airflow_skills_sha256": _sha_dir(re_.REPO_ROOT / "skills" / "airflow"),
            "campaigns": [{"dir": str(d), **{k: m.get(k) for k in (
                "arm", "models", "runner", "altimate_code_version", "airflow_skills_sha256", "repo_head",
                "started_at")}} for d in args.dirs
                for m in [json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}]],
            "n_attempts": len(records), "n_attempts_with_events": sum(x["events_available"] for x in records),
            "n_runs": {k: len(v) for k, v in variants.items()}, "flag_counts": _counts(records)}
    san.write_json(args.out / "meta.json", meta)
    md = render_summary(records, reports, meta) + "\n".join(render_extra(reports))
    san.write_text(args.out / "REPORT.md", md)
    keep = ("split", "arm", "model", "n_valid", "pass_rate", "n_runs", "statuses")
    san.write_json(args.out / "results.json", {
        "meta": meta,
        "strong_attempts": [{k: x.get(k) for k in ("split", "arm", "model", "case", "run", "status", "source")}
                            | {"hits": [h for h in x["hits"] if h["strength"] == "strong"]}
                            for x in records if x["scored"] and x.get("evidence_strength") == "strong"],
        "tables": {name: {"n_runs": res["n_runs"],
                          "by_split_arm_model": [{k: r.get(k) for k in keep} for r in res["by_split_arm_model"]],
                          "paired_deltas": [{k: v for k, v in d.items() if k != "cases"} for d in res["paired_deltas"]],
                          "pooled_deltas": res["pooled_deltas"]}
                   for name, res in reports.items()},
        "per_case_deltas": per_case_deltas(reports),
        "conclusion_check": conclusion_check(reports),
    })
    print(san.sanitize_text(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
