#!/usr/bin/env python3
"""Aggregate eval result directories into results.json + REPORT.md.

Usage::

    python3 evals/harness/report.py evals/airflow/results/haiku-baseline-dev \
        evals/airflow/results/haiku-skill-dev --out evals/airflow/results/summary-dev

Each input directory is a ``run_eval.py --out`` directory (``meta.json`` +
``runs.jsonl``). Rows for the same (case, arm, model, run) from several dirs are
merged: a ``skipped_budget`` row yields to a launched run from another dir, and
two launched rows for one run abort the report (use ``run_eval.py --run-offset``
to add runs to an earlier campaign). Spend is never dropped: a ``skipped_budget``
row whose earlier attempts were paid (e.g. infra errors) has its cost folded into
the launched row that replaces it; only genuinely unlaunched placeholders are
discarded.

Merged dirs must agree on each case's split, area, Airflow version and content
hash, and skill-arm dirs on the ``skills/airflow`` hash; otherwise the report
aborts unless ``--allow-mixed`` is passed (the conflicts are then listed).

Rows are grouped by (case, arm, model). Pass rates use only *valid* runs: final
status ``infra_error``, ``grader_error``, ``harness_error`` and ``skipped_budget``
are excluded from rates and reported separately. Timeouts, turn limits and cost
limits count as failures. Runs flagged ``contamination_suspect`` and agent-env
restores are listed in an Isolation section.

The paired delta (skill - baseline) is computed per model and split over cases
that have valid runs in both arms; the 95% CI is a percentile bootstrap over
cases. The pooled delta (all models together, per split) averages every
(case, model) pair, and its CI is a case-clustered bootstrap: cases are
resampled, each carrying the deltas of all its models, because the models'
results on one case are not independent.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sanitize as san  # noqa: E402

#: Unlaunched placeholders: campaign budget, usage-limit stop (claude-code), setup abort.
SKIPPED = ("skipped_budget", "skipped_usage_limit", "skipped_abort")
INVALID = ("infra_error", "grader_error", "harness_error", *SKIPPED)
CASE_META_KEYS = ("sha256", "split", "area", "airflow_version")


def load_rows(dirs: list[Path]) -> tuple[list[dict], list[dict]]:
    rows, metas = [], []
    for d in dirs:
        meta_path, runs_path = d / "meta.json", d / "runs.jsonl"
        if not runs_path.exists():
            raise SystemExit(f"{d}: no runs.jsonl")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        metas.append({"dir": str(d), **{k: meta.get(k) for k in (
            "run_name", "arm", "runner", "models", "split", "started_at", "finished_at", "altimate_code_version",
            "claude_code_version",
            "envs", "airflow_skills_sha256", "staged_skills_sha256", "harness_sha256", "repo_head", "budget",
            "status_counts", "isolation", "cases")}})
        for line in runs_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                row["_source"] = str(d)
                rows.append(row)
    return rows, metas


def check_consistency(metas: list[dict], rows: list[dict]) -> list[str]:
    """Conflicts between merged result dirs (empty list = consistent).

    - a case whose split/area/airflow_version/sha256 differs between dirs' ``meta.json``
      ``cases`` (or whose rows disagree on split/area/airflow_version);
    - skill-arm dirs built from different ``skills/airflow`` revisions.
    """
    problems: list[str] = []
    seen: dict[tuple[str, str], dict[Any, list[str]]] = defaultdict(lambda: defaultdict(list))
    for m in metas:
        for cid, info in (m.get("cases") or {}).items():
            for k in CASE_META_KEYS:
                seen[(cid, k)][(info or {}).get(k)].append(m["dir"])
    for r in rows:
        for k in ("split", "area", "airflow_version"):
            if r.get(k) is not None:
                seen[(r["case"], k)][r.get(k)].append(r.get("_source", "?"))
    for (cid, k), values in sorted(seen.items()):
        vals = {v: srcs for v, srcs in values.items() if v is not None}
        if len(vals) > 1:
            detail = "; ".join(f"{v!r} in {sorted(set(s))}" for v, s in vals.items())
            problems.append(f"case {cid}: conflicting {k}: {detail}")
    runners = defaultdict(list)
    for m in metas:
        runners[m.get("runner") or "altimate-code"].append(m["dir"])
    if len(runners) > 1:
        problems.append("dirs come from different agent runners: "
                        + "; ".join(f"{k} in {v}" for k, v in sorted(runners.items())))
    skill_revs = defaultdict(list)
    for m in metas:
        if m.get("arm") == "skill" and m.get("airflow_skills_sha256"):
            skill_revs[m["airflow_skills_sha256"]].append(m["dir"])
    if len(skill_revs) > 1:
        problems.append("skill arm dirs use different skills/airflow revisions: "
                        + "; ".join(f"{h[:12]} in {d}" for h, d in skill_revs.items()))
    # The full staged skill set (repo skills both arms load) must match within an arm.
    staged: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for m in metas:
        if m.get("arm") and m.get("staged_skills_sha256"):
            staged[m["arm"]][m["staged_skills_sha256"]].append(m["dir"])
    for arm, revs in sorted(staged.items()):
        if len(revs) > 1:
            problems.append(f"{arm} arm dirs staged different skill sets: "
                            + "; ".join(f"{h[:12]} in {d}" for h, d in revs.items()))
    return problems


def _paid(r: dict) -> bool:
    """True if a row cost money or launched any attempt."""
    return bool((r.get("cost_usd") or 0) > 0 or any(
        a.get("launched") or a.get("status") not in (None, *SKIPPED) for a in r.get("attempts") or []))


def _fold_cost(keep: dict, other: dict) -> dict:
    """``keep`` plus the spend of a superseded row for the same run."""
    merged = dict(keep)
    for k in ("cost_usd", "cost_reported_usd"):
        merged[k] = round((keep.get(k) or 0) + (other.get(k) or 0), 6)
    merged["superseded_cost_usd"] = round((keep.get("superseded_cost_usd") or 0) + (other.get("cost_usd") or 0), 6)
    merged["retries"] = (keep.get("retries") or 0) + sum(
        1 for a in other.get("attempts") or [] if a.get("status") not in (None, *SKIPPED))
    merged["merged_from"] = sorted({*keep.get("merged_from", []), other.get("_source", "?")})
    for flag in ("contamination_suspect", "kill_command", "agent_env_restored", "agent_env_restore_failed"):
        merged[flag] = bool(keep.get(flag) or other.get(flag))
    merged["attempts"] = [dict(a, superseded_from=other.get("_source", "?")) for a in other.get("attempts") or []
                          if a.get("status") not in SKIPPED] + list(keep.get("attempts") or [])
    return merged


def dedupe_runs(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Merge rows for the same (case, arm, model, run) coming from several result dirs.

    A row whose final status is ``skipped_budget`` yields to a launched row for the
    same run from another dir (e.g. a follow-up ``--run-offset`` campaign). If the
    yielding row had paid attempts (infra errors before the budget ran out), its
    cost is folded into the kept row; only unpaid placeholders are discarded.
    Two launched rows for one run are a collision and abort the report.
    Returns (kept rows, superseded rows).
    """
    by_run: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_run[(r["case"], r["arm"], r["model"], r.get("run"))].append(r)
    kept, dropped, collisions = [], [], []
    for key, group in by_run.items():
        if key[3] is None or len(group) == 1:
            kept.extend(group)
            continue
        launched = [r for r in group if r.get("status") not in SKIPPED]
        if len(launched) > 1:
            collisions.append(f"{key}: " + ", ".join(sorted(r.get("_source", "?") for r in launched)))
            continue
        base = launched[0] if launched else group[0]
        keep = base
        for other in group:
            if other is base:
                continue
            if _paid(other):
                keep = _fold_cost(keep, other)
            dropped.append(other)
        kept.append(keep)
    if collisions:
        raise SystemExit("duplicate launched runs across result dirs (use run_eval.py --run-offset):\n  "
                         + "\n  ".join(sorted(collisions)))
    return kept, dropped


def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 4) if xs else None


def group_stats(rows: list[dict]) -> dict[str, Any]:
    """Statistics for runs of one (case, arm, model)."""
    valid = [r for r in rows if r.get("status") not in INVALID]
    skills = Counter(s for r in valid for s in (r.get("airflow_skills_used") or []))
    tokens = [r.get("tokens") or {} for r in valid]
    return {
        "n_runs": len(rows),
        "n_valid": len(valid),
        "n_excluded": len(rows) - len(valid),
        "pass_rate": _mean([1.0 if r.get("primary_pass") else 0.0 for r in valid]),
        "mean_primary_score": _mean([r.get("primary_score") or 0.0 for r in valid]),
        "mean_secondary_score": _mean([r.get("secondary_score") for r in valid]),
        "trigger_rate": _mean([1.0 if r.get("airflow_skills_used") else 0.0 for r in valid]),
        "skills_used": dict(skills),
        "mean_tokens_total": _mean([t.get("total") for t in tokens]),
        "mean_tokens_input": _mean([t.get("input") for t in tokens]),
        "mean_tokens_output": _mean([t.get("output") for t in tokens]),
        "mean_cost_usd": _mean([r.get("cost_usd") for r in valid]),
        "total_cost_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 4),
        "contamination_suspect_runs": sum(1 for r in rows if r.get("contamination_suspect")),
        "mean_wall_s": _mean([r.get("wall_s") for r in valid]),
        "statuses": dict(Counter(r.get("status") for r in rows)),
        "retries": sum(r.get("retries") or 0 for r in rows),
    }


def bootstrap_ci(values: list[float], iters: int = 10000, seed: int = 0, alpha: float = 0.05) -> tuple:
    """Percentile bootstrap CI of the mean. Returns (low, high) or (None, None) if empty."""
    if not values:
        return (None, None)
    if len(values) == 1:
        return (values[0], values[0])
    rng = random.Random(seed)
    n = len(values)
    means = sorted(statistics.fmean(rng.choices(values, k=n)) for _ in range(iters))
    lo = means[int((alpha / 2) * iters)]
    hi = means[min(iters - 1, int((1 - alpha / 2) * iters))]
    return (round(lo, 4), round(hi, 4))


def cluster_bootstrap_ci(clusters: list[list[float]], iters: int = 10000, seed: int = 0,
                         alpha: float = 0.05) -> tuple:
    """Percentile bootstrap CI of the mean over all values, resampling whole clusters.

    Each resample draws ``len(clusters)`` clusters with replacement and takes the
    mean of every value they carry. Returns (low, high) or (None, None) if empty.
    """
    clusters = [list(c) for c in clusters if c]
    if not clusters:
        return (None, None)
    if len(clusters) == 1:
        m = round(statistics.fmean(clusters[0]), 4)
        return (m, m)
    rng = random.Random(seed)
    sums = [(sum(c), len(c)) for c in clusters]
    means = []
    for _ in range(iters):
        draw = rng.choices(sums, k=len(sums))
        means.append(sum(t for t, _ in draw) / sum(n for _, n in draw))
    means.sort()
    lo = means[int((alpha / 2) * iters)]
    hi = means[min(iters - 1, int((1 - alpha / 2) * iters))]
    return (round(lo, 4), round(hi, 4))


def pooled_deltas(per_model: list[dict], iters: int, seed: int) -> list[dict]:
    """Per split: mean delta over all (case, model) pairs; the CI resamples cases."""
    out = []
    for split in ("dev", "holdout"):
        by_case: dict[str, list[dict]] = defaultdict(list)
        for d in per_model:
            if d["split"] == split:
                for c in d["cases"]:
                    by_case[c["case"]].append(c)
        if not by_case:
            continue
        cases = sorted(by_case)
        d_pass = [[c["delta_pass_rate"] for c in by_case[k]] for k in cases]
        d_score = [[c["delta_primary_score"] for c in by_case[k]] for k in cases]
        out.append({
            "split": split, "n_cases": len(cases), "n_pairs": sum(len(v) for v in d_pass),
            "models": sorted({d["model"] for d in per_model if d["split"] == split}),
            "mean_delta_pass_rate": _mean([x for v in d_pass for x in v]),
            "ci95_delta_pass_rate": cluster_bootstrap_ci(d_pass, iters, seed),
            "mean_delta_primary_score": _mean([x for v in d_score for x in v]),
            "ci95_delta_primary_score": cluster_bootstrap_ci(d_score, iters, seed),
            "ci_method": "percentile bootstrap over cases; a resampled case carries all its models",
        })
    return out


def paired_deltas(groups: dict, meta_by_case: dict, iters: int, seed: int) -> list[dict]:
    """Per (model, split): mean over cases of skill - baseline pass rate and primary score."""
    out = []
    models = sorted({m for (_, _, m) in groups})
    for model in models:
        for split in ("dev", "holdout"):
            per_case = []
            for case in sorted({c for (c, _, m) in groups if m == model}):
                if meta_by_case.get(case, {}).get("split") != split:
                    continue
                b, s = groups.get((case, "baseline", model)), groups.get((case, "skill", model))
                if not b or not s or b["pass_rate"] is None or s["pass_rate"] is None:
                    continue
                per_case.append({
                    "case": case,
                    "baseline_pass_rate": b["pass_rate"], "skill_pass_rate": s["pass_rate"],
                    "delta_pass_rate": round(s["pass_rate"] - b["pass_rate"], 4),
                    "delta_primary_score": round((s["mean_primary_score"] or 0) - (b["mean_primary_score"] or 0), 4),
                })
            if not per_case:
                continue
            d_pass = [c["delta_pass_rate"] for c in per_case]
            d_score = [c["delta_primary_score"] for c in per_case]
            out.append({
                "model": model, "split": split, "n_cases": len(per_case),
                "mean_delta_pass_rate": _mean(d_pass),
                "ci95_delta_pass_rate": bootstrap_ci(d_pass, iters, seed),
                "mean_delta_primary_score": _mean(d_score),
                "ci95_delta_primary_score": bootstrap_ci(d_score, iters, seed),
                "cases": per_case,
            })
    return out


def aggregate(rows: list[dict], iters: int = 10000, seed: int = 0) -> dict:
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    case_meta: dict[str, dict] = {}
    for r in rows:
        by_key[(r["case"], r["arm"], r["model"])].append(r)
        case_meta.setdefault(r["case"], {"split": r.get("split"), "area": r.get("area"),
                                         "airflow_version": r.get("airflow_version")})
    groups = {k: group_stats(v) for k, v in sorted(by_key.items())}
    arm_model: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        arm_model[(r.get("split"), r["arm"], r["model"])].append(r)
    per_model = paired_deltas(groups, case_meta, iters, seed)
    return {
        "groups": [{"case": c, "arm": a, "model": m, **case_meta[c], **st} for (c, a, m), st in groups.items()],
        "by_split_arm_model": [{"split": s, "arm": a, "model": m, **group_stats(v)}
                               for (s, a, m), v in sorted(arm_model.items(), key=lambda kv: tuple(map(str, kv[0])))],
        "paired_deltas": per_model,
        "pooled_deltas": pooled_deltas(per_model, iters, seed),
        "failure_classes": dict(Counter(r.get("status") for r in rows)),
        "total_cost_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 4),
        "isolation": {
            "contamination_suspects": [
                {k: r.get(k) for k in ("case", "arm", "model", "run", "status", "_source")}
                | {"hits": [h for a in r.get("attempts") or []
                            for h in ((a.get("isolation") or {}).get("hits") or [])][:10]}
                for r in rows if r.get("contamination_suspect")],
            "kill_command_runs": [
                {k: r.get(k) for k in ("case", "arm", "model", "run", "status")}
                | {"commands": [k["command"][:120] for a in r.get("attempts") or []
                                for k in ((a.get("isolation") or {}).get("kill_commands") or [])][:5]}
                for r in rows if r.get("kill_command")],
            "agent_env_restored_runs": [
                {k: r.get(k) for k in ("case", "arm", "model", "run")} for r in rows if r.get("agent_env_restored")],
            "agent_env_restore_failed_runs": [
                {k: r.get(k) for k in ("case", "arm", "model", "run")} for r in rows
                if r.get("agent_env_restore_failed")],
        },
    }


def _fmt(v: Any, pct: bool = False) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v * 100:.0f}%" if pct else f"{v:.3g}"
    return str(v)


def render_markdown(result: dict) -> str:
    lines = ["# Airflow skill eval report", ""]
    lines += ["Pass rate = fraction of valid runs whose primary checks all passed. Excluded runs "
              "(infra_error, grader_error, skipped_budget) are listed but not counted.", ""]
    for split in ("dev", "holdout"):
        rows = [r for r in result["by_split_arm_model"] if r["split"] == split]
        if not rows:
            continue
        lines += [f"## {split}: by arm and model", "",
                  "| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r['arm']} | {r['model']} | {r['n_runs']} ({r['n_valid']}) | {_fmt(r['pass_rate'], True)} | "
                         f"{_fmt(r['mean_primary_score'])} | {_fmt(r['mean_secondary_score'])} | "
                         f"{_fmt(r['trigger_rate'], True)} | {_fmt(r['mean_tokens_total'])} | "
                         f"{_fmt(r['mean_cost_usd'])} | {_fmt(r['mean_wall_s'])} | {r['statuses']} |")
        lines.append("")
        deltas = [d for d in result["paired_deltas"] if d["split"] == split]
        if deltas:
            lines += [f"## {split}: paired delta (skill - baseline) over cases", "",
                      "| model | cases | delta pass rate | 95% CI | delta primary score | 95% CI |", "|---|---|---|---|---|---|"]
            for d in deltas:
                lines.append(f"| {d['model']} | {d['n_cases']} | {_fmt(d['mean_delta_pass_rate'])} | "
                             f"{d['ci95_delta_pass_rate']} | {_fmt(d['mean_delta_primary_score'])} | "
                             f"{d['ci95_delta_primary_score']} |")
            pooled = [x for x in result.get("pooled_deltas") or [] if x["split"] == split]
            for d in pooled:
                lines.append(f"| pooled ({d['n_pairs']} case x model pairs) | {d['n_cases']} | "
                             f"{_fmt(d['mean_delta_pass_rate'])} | {d['ci95_delta_pass_rate']} | "
                             f"{_fmt(d['mean_delta_primary_score'])} | {d['ci95_delta_primary_score']} |")
            lines.append("")
            if pooled:
                lines += ["Pooled CI: bootstrap over cases; a resampled case carries the deltas of all its models.", ""]
        lines += [f"## {split}: per case", "",
                  "| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for gr in result["groups"]:
            if gr["split"] != split:
                continue
            lines.append(f"| {gr['case']} | {gr['area']} | {gr['arm']} | {gr['model']} | {gr['n_runs']} ({gr['n_valid']}) | "
                         f"{_fmt(gr['pass_rate'], True)} | {_fmt(gr['mean_primary_score'])} | "
                         f"{_fmt(gr['mean_secondary_score'])} | {gr['skills_used'] or '-'} | "
                         f"{_fmt(gr['mean_cost_usd'])} | {gr['statuses']} |")
        lines.append("")
    lines += ["## Failure classes (all runs)", "", str(result["failure_classes"]), ""]
    lines += [f"Total spend (all attempts, all dirs): ${result.get('total_cost_usd', 0):.2f}", ""]
    if result.get("superseded_placeholders"):
        lines += [f"{len(result['superseded_placeholders'])} skipped_budget row(s) were replaced by "
                  "launched runs from another result dir; their spend is kept on the replacing row.", ""]
    iso = result.get("isolation") or {}
    sus = iso.get("contamination_suspects") or []
    lines += ["## Isolation", "", f"Contamination suspects: {len(sus)} run(s)." + ("" if sus else " None.")]
    for x in sus:
        paths = ", ".join(f"{h['tool']}:{h['path']} ({h['root']})" for h in x["hits"][:5])
        lines.append(f"- {x['case']} {x['arm']} {x['model']} run {x['run']}: {paths}")
    kills = iso.get("kill_command_runs") or []
    lines.append(f"Broad kill commands (pkill/killall/kill by pattern): {len(kills)} run(s)."
                 + ("" if kills else " None."))
    for x in kills:
        lines.append(f"- {x['case']} {x['arm']} {x['model']} run {x['run']}: " + " ; ".join(x["commands"][:3]))
    lines.append(f"Agent env restored after: {len(iso.get('agent_env_restored_runs') or [])} run(s); "
                 f"restore failed: {len(iso.get('agent_env_restore_failed_runs') or [])}.")
    if result.get("consistency_warnings"):
        lines += ["", "Merged with --allow-mixed despite these conflicts:"]
        lines += [f"- {w}" for w in result["consistency_warnings"]]
    lines.append("")
    lines += ["## Sources", ""]
    for m in result.get("sources", []):
        agent = (f"claude-code={m.get('claude_code_version')}" if m.get("runner") == "claude-code"
                 else f"altimate-code={m.get('altimate_code_version')}")
        lines.append(f"- `{m['dir']}`: arm={m.get('arm')} models={m.get('models')} {agent} "
                     f"started={m.get('started_at')} budget={m.get('budget')}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", type=Path, help="run_eval.py result directories")
    ap.add_argument("--out", type=Path, required=True, help="where to write results.json and REPORT.md")
    ap.add_argument("--bootstrap", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--allow-mixed", action="store_true",
                    help="merge dirs even if case splits/revisions or skill revisions conflict")
    args = ap.parse_args(argv)
    rows, metas = load_rows(args.dirs)
    conflicts = check_consistency(metas, rows)
    if conflicts and not args.allow_mixed:
        raise SystemExit("result dirs disagree (pass --allow-mixed to merge anyway):\n  " + "\n  ".join(conflicts))
    rows, dropped = dedupe_runs(rows)
    result = aggregate(rows, args.bootstrap, args.seed)
    result["sources"] = [{k: v for k, v in m.items() if k != "cases"} for m in metas]
    result["consistency_warnings"] = conflicts
    result["superseded_placeholders"] = [
        {k: r.get(k) for k in ("case", "arm", "model", "run", "status", "cost_usd", "_source")} for r in dropped]
    args.out.mkdir(parents=True, exist_ok=True)
    san.write_json(args.out / "results.json", result)
    md = san.sanitize_text(render_markdown(result))
    (args.out / "REPORT.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
