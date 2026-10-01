#!/usr/bin/env python3
"""Trigger evals: does the right Airflow skill fire, and does it stay quiet otherwise?

Each query in ``queries.json`` runs once per (model, run) in a fresh copy of its
fixture, with the same isolation as ``run_eval.py`` in the skill arm (all repo
skills plus ``skills/airflow``). The agent gets a few turns only; nothing is
graded except which skills it invoked through the ``skill`` tool (plus any
auto-loaded skills found in the altimate-code trace).

Example::

    PY=~/.cache/des-evals/airflow-3.3/bin/python
    $PY evals/harness/run_triggers.py --queries evals/airflow/triggers/queries.json \
        --models google-vertex-anthropic/claude-sonnet-4-6@default,google-vertex-anthropic/claude-haiku-4-5@20251001 \
        --runs 2 --max-turns 4 --max-cost-usd 40 --out evals/airflow/results/triggers-2026-09-30

    # re-render the report from an existing runs.jsonl
    $PY evals/harness/run_triggers.py --report-only --out evals/airflow/results/triggers-2026-09-30
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import sys
import threading
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS_DIR))
import claude_code as cc  # noqa: E402
import grading as g  # noqa: E402
import isolation as iso  # noqa: E402
import run_eval as r  # noqa: E402
import sanitize as san  # noqa: E402

REPO_ROOT = r.REPO_ROOT
DEFAULT_QUERIES = REPO_ROOT / "evals/airflow/triggers/queries.json"
#: venv used to build the agent env for contexts without an Airflow version; its
#: activation is then stripped (see :func:`deactivate_airflow`).
FALLBACK_AIRFLOW_VERSION = "3.3"
NOT_SCORED = ("infra_error", "skipped_budget", "harness_error", "skipped_usage_limit", "skipped_abort")


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------


def load_queries(path: Path, airflow_names: list[str] | None = None) -> tuple[dict, list[dict]]:
    """``(contexts, queries)`` from ``queries.json``; raises ``ValueError`` listing every problem.

    Fixture paths are resolved relative to the file. When ``airflow_names`` is
    given, every non-null ``expected`` must be one of them.
    """
    data = json.loads(Path(path).read_text())
    base = Path(path).resolve().parent
    return validate_queries(data, base, airflow_names)


def validate_queries(data: dict, base: Path, airflow_names: list[str] | None = None) -> tuple[dict, list[dict]]:
    problems = []
    contexts = {}
    for name, spec in (data.get("contexts") or {}).items():
        fixture = (base / str(spec.get("fixture", ""))).resolve()
        if not spec.get("fixture") or not fixture.is_dir():
            problems.append(f"context {name!r}: fixture {fixture} is not a directory")
        version = spec.get("airflow_version")
        if version is not None and str(version) not in g.ENV_DIRS:
            problems.append(f"context {name!r}: airflow_version must be null or one of {sorted(g.ENV_DIRS)}")
        contexts[name] = {"fixture": fixture, "airflow_version": None if version is None else str(version)}
    queries = data.get("queries") or []
    seen = set()
    for i, q in enumerate(queries):
        qid = q.get("id") or f"#{i}"
        if not q.get("id"):
            problems.append(f"query {qid}: missing id")
        elif qid in seen:
            problems.append(f"query {qid}: duplicate id")
        seen.add(qid)
        if not str(q.get("query") or "").strip():
            problems.append(f"query {qid}: missing query text")
        if q.get("context") not in contexts:
            problems.append(f"query {qid}: unknown context {q.get('context')!r}")
        if "expected" not in q:
            problems.append(f"query {qid}: missing expected (use null for near-misses)")
        elif q["expected"] is not None and airflow_names is not None and q["expected"] not in airflow_names:
            problems.append(f"query {qid}: expected {q['expected']!r} is not an airflow skill {airflow_names}")
    if not queries:
        problems.append("no queries")
    if problems:
        raise ValueError("; ".join(problems))
    return contexts, queries


# --------------------------------------------------------------------------
# Scoring (pure)
# --------------------------------------------------------------------------


def fired_skills(skill_invocations: list[dict], auto_loaded: list[str] = ()) -> list[str]:
    """Distinct skill names in first-invocation order (skill tool calls, then auto-loads)."""
    out: list[str] = []
    for name in [s.get("name") for s in skill_invocations] + list(auto_loaded):
        if name and name not in out:
            out.append(name)
    return out


def classify_trigger(expected: str | None, fired: list[str], airflow_names: list[str]) -> str:
    """Outcome of one run.

    Should-fire query (``expected`` set):
      ``hit`` expected fired and no other airflow skill; ``hit_plus`` expected
      fired together with another airflow skill; ``confused`` only a different
      airflow skill fired; ``miss`` no airflow skill fired.
    Near-miss (``expected`` None): ``false_fire`` any airflow skill fired, else ``quiet``.
    """
    af = [s for s in fired if s in airflow_names]
    if expected is None:
        return "false_fire" if af else "quiet"
    if expected in af:
        return "hit_plus" if len(af) > 1 else "hit"
    return "confused" if af else "miss"


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def compute_metrics(rows: list[dict], airflow_names: list[str]) -> dict:
    """Per-skill recall / precision / confusion / false-fire over scored rows.

    ``rows`` need ``expected``, ``fired`` (list) and ``status``; rows whose status
    is in ``NOT_SCORED`` are counted separately and excluded.
    """
    scored = [x for x in rows if x.get("status") not in NOT_SCORED]
    near = [x for x in scored if x["expected"] is None]
    per_skill = {}
    for s in airflow_names:
        pos = [x for x in scored if x["expected"] == s]
        fired_s = [x for x in scored if s in x["fired"]]
        wrong = [x for x in pos if any(o in x["fired"] for o in airflow_names if o != s)]
        per_skill[s] = {
            "should_fire_runs": len(pos),
            "fired_when_expected": sum(1 for x in pos if s in x["fired"]),
            "recall": _ratio(sum(1 for x in pos if s in x["fired"]), len(pos)),
            "runs_where_fired": len(fired_s),
            "precision": _ratio(sum(1 for x in fired_s if x["expected"] == s), len(fired_s)),
            "wrong_airflow_skill_on_own_queries": len(wrong),
            "confusion_rate": _ratio(len(wrong), len(pos)),
            "fired_on_other_airflow_queries": sum(1 for x in fired_s if x["expected"] not in (None, s)),
            "near_miss_false_fires": sum(1 for x in near if s in x["fired"]),
            "near_miss_false_fire_rate": _ratio(sum(1 for x in near if s in x["fired"]), len(near)),
        }
    labels = [*airflow_names, None]
    matrix = {
        str(e): {
            **{f: sum(1 for x in scored if x["expected"] == e and f in x["fired"]) for f in airflow_names},
            "(no airflow skill)": sum(1 for x in scored if x["expected"] == e
                                      and not any(f in x["fired"] for f in airflow_names)),
            "runs": sum(1 for x in scored if x["expected"] == e),
        }
        for e in labels
    }
    outcomes: dict[str, int] = {}
    for x in scored:
        o = classify_trigger(x["expected"], x["fired"], airflow_names)
        outcomes[o] = outcomes.get(o, 0) + 1
    return {
        "scored_runs": len(scored),
        "unscored_runs": {st: sum(1 for x in rows if x.get("status") == st) for st in NOT_SCORED
                          if any(x.get("status") == st for x in rows)},
        "per_skill": per_skill,
        "near_miss": {
            "runs": len(near),
            "any_airflow_false_fires": sum(1 for x in near if any(f in x["fired"] for f in airflow_names)),
            "false_fire_rate": _ratio(sum(1 for x in near if any(f in x["fired"] for f in airflow_names)),
                                      len(near)),
        },
        "confusion_matrix": matrix,
        "outcomes": outcomes,
    }


def per_query(rows: list[dict], airflow_names: list[str]) -> list[dict]:
    """One line per query: outcomes and fired skills per run, grouped by model."""
    by_q: dict[str, dict] = {}
    for x in sorted(rows, key=lambda x: (x["query_id"], x["model"], x["run"])):
        q = by_q.setdefault(x["query_id"], {"query_id": x["query_id"], "expected": x["expected"],
                                            "context": x["context"], "query": x["query"], "runs": []})
        q["runs"].append({
            "model": x["model"], "run": x["run"], "status": x.get("status"), "fired": x["fired"],
            "outcome": (None if x.get("status") in NOT_SCORED
                        else classify_trigger(x["expected"], x["fired"], airflow_names)),
        })
    return list(by_q.values())


def notable_misfires(rows: list[dict], airflow_names: list[str]) -> list[dict]:
    """Scored runs whose outcome is miss / confused / hit_plus / false_fire."""
    bad = []
    for x in rows:
        if x.get("status") in NOT_SCORED:
            continue
        o = classify_trigger(x["expected"], x["fired"], airflow_names)
        if o in ("miss", "confused", "hit_plus", "false_fire"):
            bad.append({"query_id": x["query_id"], "model": x["model"], "run": x["run"], "outcome": o,
                        "expected": x["expected"], "fired": x["fired"], "query": x["query"]})
    return sorted(bad, key=lambda b: (b["outcome"], b["query_id"], b["model"], b["run"]))


def _pct(v: float | None) -> str:
    return "-" if v is None else f"{v * 100:.0f}%"


def render_report(summary: dict) -> str:
    """Markdown report from ``summary.json`` contents."""
    names = summary["airflow_skill_names"]
    lines = [f"# Airflow skill trigger eval: {summary['run_name']}", ""]
    meta = summary.get("meta", {})
    lines += [
        f"- Models: {', '.join(summary['models'])}; runs per query: {meta.get('runs_per_query')}; "
        f"max turns: {meta.get('max_turns')}",
        f"- Queries: {summary['n_queries']} ({summary['n_should_fire']} should-fire, "
        f"{summary['n_near_miss']} near-miss); skill arm (repo skills + skills/airflow)",
        f"- skills/airflow sha256: `{meta.get('airflow_skills_sha256')}`",
        f"- Spent: ${meta.get('spent_usd', 0):.2f} of ${meta.get('cap_usd', 0):.2f} cap",
        "",
        "Recall = should-fire runs where the expected skill fired. Precision = runs where the skill fired "
        "that expected it. Confusion = the skill's own should-fire runs where a different Airflow skill "
        "fired. Near-miss false-fire = near-miss runs where the skill fired.",
        "",
    ]
    for scope, m in [("All models", summary["overall"]), *summary["by_model"].items()]:
        lines += [f"## {scope}", "",
                  "| Skill | Recall | Precision | Confusion | Near-miss false-fire |",
                  "|---|---|---|---|---|"]
        for s in names:
            p = m["per_skill"][s]
            lines.append(
                f"| {s} | {p['fired_when_expected']}/{p['should_fire_runs']} ({_pct(p['recall'])}) "
                f"| {_pct(p['precision'])} ({p['runs_where_fired']} fired) "
                f"| {p['wrong_airflow_skill_on_own_queries']}/{p['should_fire_runs']} ({_pct(p['confusion_rate'])}) "
                f"| {p['near_miss_false_fires']}/{m['near_miss']['runs']} "
                f"({_pct(p['near_miss_false_fire_rate'])}) |")
        nm = m["near_miss"]
        lines += ["", f"Any Airflow skill on near-misses: {nm['any_airflow_false_fires']}/{nm['runs']} "
                  f"({_pct(nm['false_fire_rate'])}). Outcomes: {json.dumps(m['outcomes'], sort_keys=True)}."]
        if m["unscored_runs"]:
            lines.append(f"Unscored runs: {json.dumps(m['unscored_runs'])}.")
        lines.append("")
    lines += ["## Confusion matrix (all models, runs)", "",
              "| expected \\ fired | " + " | ".join(names) + " | (no airflow skill) | runs |",
              "|---" * (len(names) + 3) + "|"]
    for e, row in summary["overall"]["confusion_matrix"].items():
        label = "near-miss (none)" if e == "None" else e
        lines.append(f"| {label} | " + " | ".join(str(row[n]) for n in names)
                     + f" | {row['(no airflow skill)']} | {row['runs']} |")
    lines += ["", "## Per query", "", "| Query | Context | Expected | Runs (model:run outcome [fired]) |",
              "|---|---|---|---|"]
    for q in summary["per_query"]:
        runs = "; ".join(
            f"{_short_model(x['model'])}:{x['run']} {x['outcome'] or x['status']}"
            + (f" [{', '.join(x['fired'])}]" if x["fired"] else "")
            for x in q["runs"])
        lines.append(f"| {q['query_id']} | {q['context']} | {q['expected'] or '-'} | {runs} |")
    lines += ["", "## Notable misfires", ""]
    if not summary["misfires"]:
        lines.append("None.")
    for b in summary["misfires"]:
        lines.append(f"- **{b['outcome']}** `{b['query_id']}` ({_short_model(b['model'])} run {b['run']}): "
                     f"expected {b['expected'] or 'none'}, fired {b['fired'] or 'nothing'}. "
                     f"Query: \"{b['query']}\"")
    return "\n".join(lines) + "\n"


def _short_model(model: str) -> str:
    """``google-vertex-anthropic/claude-sonnet-5-5@default`` -> ``sonnet-5-5``."""
    return g.model_key(model).removeprefix("claude-")


def build_summary(rows: list[dict], airflow_names: list[str], queries: list[dict], models: list[str],
                  run_name: str, meta: dict) -> dict:
    return {
        "run_name": run_name,
        "airflow_skill_names": airflow_names,
        "models": models,
        "n_queries": len(queries),
        "n_should_fire": sum(1 for q in queries if q["expected"]),
        "n_near_miss": sum(1 for q in queries if not q["expected"]),
        "meta": meta,
        "overall": compute_metrics(rows, airflow_names),
        "by_model": {m: compute_metrics([x for x in rows if x["model"] == m], airflow_names) for m in models},
        "per_query": per_query(rows, airflow_names),
        "misfires": notable_misfires(rows, airflow_names),
    }


# --------------------------------------------------------------------------
# Agent env
# --------------------------------------------------------------------------


def deactivate_airflow(env: dict[str, str], env_py: str) -> dict[str, str]:
    """Undo the Airflow venv activation ``run_eval.build_agent_env`` applies (non-Airflow contexts).

    ``PIP_REQUIRE_VIRTUALENV`` and the per-attempt dirs stay, so a host pip still refuses to install."""
    venv_bin = str(Path(env_py).parent)
    out = {k: v for k, v in env.items() if not k.startswith("AIRFLOW") and k != "VIRTUAL_ENV"}
    out["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if p != venv_bin)
    return out


def make_workspace(fixture: Path, parent: Path) -> Path:
    ws = parent / "ws"
    shutil.copytree(fixture, ws, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    r.git(ws, "init", "-q", "-b", "main")
    r.git(ws, "add", "-A")
    r.git(ws, "commit", "-q", "-m", "initial project state")
    return ws


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------


def run_attempt(q: dict, ctx: dict, model: str, attempt_dir: Path, skills_dir: Path,
                args: argparse.Namespace, budget: r.Budget) -> dict:
    """One trigger run. Always returns (and writes) a record; cost survives exceptions."""
    actx: r.AttemptContext | None = getattr(args, "ctx", None)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    version = ctx["airflow_version"] or FALLBACK_AIRFLOW_VERSION
    agent_py = g.agent_env_python(version)
    record: dict[str, Any] = {"status": "harness_error", "reason": "", "fired": [], "cost_usd": 0.0,
                              "cost_reported_usd": 0.0, "wall_s": 0.0, "launched": False}
    scratch = None
    env_lease = r.ExitStack()
    try:
        guard = (actx.env_guards if actx else {}).get(version)
        if guard is not None:
            env_lease.enter_context(guard.attempt())
        record["agent_env_pre"] = r._guard_check(actx, version)
        hook = None if ctx["airflow_version"] else (lambda env: deactivate_airflow(env, agent_py))
        prep = r.prepare_agent(f"trig-{q['id']}", agent_py, lambda d: make_workspace(ctx["fixture"], d),
                               q["query"], model, args.max_turns, skills_dir, args, env_hook=hook)
        scratch, roots = prep["scratch"], prep["roots"]
        record.update({"sandbox": bool(actx and actx.sandbox), "tmpdir": prep["env"]["TMPDIR"]})
        events_path, stderr_path = attempt_dir / "events.jsonl", attempt_dir / "stderr.log"
        correct = g.cache_correction_applies(model, actx.altimate_version if actx else "")
        cap = r.attempt_cap(actx, model, args.max_run_cost_usd)
        record["launched"] = True
        proc = r.launch_agent(prep, actx, model, events_path, stderr_path, args.timeout_s, cap, correct)
        record.update({"returncode": proc["returncode"], "wall_s": proc["wall_s"], "run_cap_usd": cap})
        events = g.load_events(events_path)
        use = g.usage(events, model, correct)
        budget.add(use["cost_usd"])
        record.update({"cost_usd": use["cost_usd"], "cost_reported_usd": use["cost_reported_usd"],
                       "cost_list_price_usd": use["cost_list_price_usd"], "cost_correction_applied": correct,
                       "double_counted_steps": use["double_counted_steps"], "steps": use["steps"],
                       "tokens": use["tokens"]})
        record.update(r.runner_fields(actx, events, use, proc, scratch))
        if proc.get("aborted"):
            raise r.AttemptAborted(proc["aborted"])
        record["agent_env_post"] = r._guard_check(actx, version, raise_on_fail=False)
        record["isolation"] = r.isolation_report(events, roots)
        record["contamination_suspect"] = record["isolation"]["contamination_suspect"]
        record["kill_command"] = bool(record["isolation"]["kill_commands"])
        stderr = stderr_path.read_text(errors="replace")
        final = r.attempt_artifact(scratch / "final.md", scratch)
        if final.exists():
            san.write_text(attempt_dir / "final.md", final.read_text(errors="replace"))
        trace = next((e.get("path") for e in reversed(events) if e.get("type") == "trace_saved"), None)
        if trace:
            trace = str(r.attempt_artifact(trace, scratch))
        invocations = g.skill_invocations(events)
        auto = r.auto_loaded_skills(trace)
        status, reason = r.classify_attempt(timed_out=proc["timed_out"], cost_capped=proc["cost_capped"],
                                            returncode=proc["returncode"], events=events, stderr=stderr,
                                            grade={"primary_pass": True, "checks": []}, grader_failed=False)
        if status == "ok":  # no grading here: "ok" only means the run produced model steps
            status, reason = ("timeout", "wall-clock timeout") if proc["timed_out"] else (
                ("cost_limit", "per-run cost cap") if proc["cost_capped"] else ("ran", "model steps completed"))
        record.update({
            "status": status,
            "reason": reason,
            "fired": fired_skills(invocations, auto),
            "skill_invocations": invocations,
            "auto_loaded_skills": auto,
            "tools": [u["tool"] for u in g.tool_uses(events)],
            "termination": {k: v for k, v in (g.termination(events) or {}).items()
                            if k in ("why_model_stopped", "why_harness_stopped", "done_reason")},
            "errors": g.error_messages(events)[-3:],
        })
    except g.UnsafeWorkspaceError as exc:
        record.update({"status": "task_fail", "reason": str(exc)[:500], "contamination_suspect": True})
    except cc.TokenCommandError as exc:  # retried like any infra error; the retry re-runs the command
        record.update({"status": "infra_error", "reason": f"token command failed: {exc}"[:500]})
        r.log(f"TOKEN COMMAND FAILED in attempt {attempt_dir}: {exc}")
    except r.AttemptAborted as exc:
        record.update({"status": "harness_error", "reason": str(exc)[:500], "aborted": True})
        if actx is not None:
            actx.abort_reason = actx.abort_reason or str(exc)
        r.log(f"ABORT in attempt {attempt_dir}: {exc}")
    except Exception as exc:  # noqa: BLE001 - keep usage/cost of a run that already happened
        import traceback

        record.update({"status": "harness_error", "reason": f"{type(exc).__name__}: {exc}"[:500],
                       "harness_exception": traceback.format_exc()[-2000:]})
        r.log(f"HARNESS EXCEPTION in attempt {attempt_dir}: {exc}")
        if scratch is not None:
            correct = g.cache_correction_applies(model, actx.altimate_version if actx else "")
            r.recover_usage(record, [attempt_dir / "events.jsonl", scratch / "events.jsonl"], model, correct)
            if record.get("usage_recovered_from"):
                budget.add(record["cost_usd"])
    finally:
        env_lease.close()
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
        san.write_json(attempt_dir / "attempt.json", record)
    return record


def new_row(q: dict, model: str, run_idx: int) -> dict:
    return {"query_id": q["id"], "context": q["context"], "expected": q["expected"],
            "query": q["query"], "model": model, "run": run_idx, "attempts": []}


def finalize_row(row: dict) -> dict:
    attempts = row["attempts"]
    final = attempts[-1] if attempts else {"status": "harness_error", "fired": []}
    row.update({"status": final["status"], "fired": final.get("fired", []),
                "cost_usd": round(sum(a.get("cost_usd") or 0 for a in attempts), 6),
                "contamination_suspect": any(a.get("contamination_suspect") for a in attempts),
                "kill_command": any(a.get("kill_command") for a in attempts),
                "killed_attempts": sum(1 for a in attempts if r.is_killed(a)),
                "retries": max(0, sum(1 for a in attempts if a.get("status") != "skipped_budget") - 1)})
    return row


def run_one(q: dict, ctx: dict, model: str, run_idx: int, out: Path, skills_dir: Path,
            args: argparse.Namespace, budget: r.Budget, row: dict | None = None) -> dict:
    row = row if row is not None else new_row(q, model, run_idx)
    run_dir = out / "runs" / q["id"] / r.slug(model) / f"run-{run_idx}"

    def launch(k: int) -> dict:
        rec = run_attempt(q, ctx, model, run_dir / f"attempt-{k}", skills_dir, args, budget)
        r.log(f"{q['id']} {_short_model(model)} run-{run_idx} attempt-{k}: fired={rec['fired']}")
        return rec

    r.attempt_loop(row, launch, getattr(args, "ctx", None), budget, f"{q['id']} {_short_model(model)} run-{run_idx}",
                   r.next_attempt_index(run_dir))
    for a in row["attempts"]:
        a.setdefault("fired", [])
    return finalize_row(row)


#: Trigger runs stop after a few turns, so their default per-run caps are a
#: fraction of the task-eval defaults (``run_eval.DEFAULT_RUN_CAP_USD``).
TRIGGER_CAP_FRACTION = 0.4


def trigger_run_cap(model: str, overrides: dict[str, float], flat: float | None) -> float:
    if model in overrides or g.model_key(model) in overrides or flat is not None:
        return r.run_cap_for(model, overrides, flat)
    return round(TRIGGER_CAP_FRACTION * r.run_cap_for(model, {}, None), 2)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    ap.add_argument("--runner", choices=r.RUNNERS, default="altimate-code",
                    help="agent CLI: altimate-code (default) or claude-code (needs CLAUDE_CODE_OAUTH_TOKEN or EVAL_CLAUDE_TOKEN_CMD)")
    ap.add_argument("--models", default=None, help="comma-separated model ids; default: the runner's defaults")
    ap.add_argument("--resume", action="store_true",
                    help="keep finished runs in --out/runs.jsonl and launch only missing or unscored ones")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--max-turns", type=int, default=4)
    ap.add_argument("--parallel", type=int, default=6)
    ap.add_argument("--query", action="append", dest="query_ids", help="run only this query id (repeatable)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--skills-dir", type=Path, default=REPO_ROOT / "skills/airflow")
    ap.add_argument("--repo-skills-dir", type=Path, default=REPO_ROOT / "skills")
    ap.add_argument("--max-cost-usd", type=float, default=40.0)
    ap.add_argument("--max-run-cost-usd", type=float, default=None,
                    help=f"per-run cap for every model; default {TRIGGER_CAP_FRACTION} x the per-model task cap")
    ap.add_argument("--max-run-cost-usd-by-model", default="", help="per-run caps as MODEL=USD,...")
    ap.add_argument("--timeout-s", type=int, default=300)
    ap.add_argument("--no-sandbox", action="store_true")
    ap.add_argument("--report-only", action="store_true", help="re-render summary/report from runs.jsonl")
    args = ap.parse_args(argv)
    for name in ("queries", "out", "skills_dir", "repo_skills_dir"):
        setattr(args, name, getattr(args, name).resolve())
    if args.models is None:
        args.models = ",".join(r.default_models(args.runner))
    try:
        args.run_cap_overrides = r.parse_cap_map(args.max_run_cost_usd_by_model)
    except ValueError as exc:
        ap.error(str(exc))
    return args


def write_report(out: Path, rows: list[dict], airflow_names: list[str], queries: list[dict], models: list[str],
                 meta: dict) -> dict:
    summary = build_summary(rows, airflow_names, queries, models, out.name, meta)
    san.write_json(out / "summary.json", summary)
    san.write_text(out / "REPORT.md", render_report(summary))
    return summary


def resume_meta_problems(meta: dict, runner: str, models: list[str],
                         provenance: dict) -> list[str]:
    """Refuse to relabel completed runs after their inputs change."""
    problems = []
    for key, now in {"runner": runner, "models": models, **provenance}.items():
        before = meta.get(key, "altimate-code" if key == "runner" else None)
        if before != now:
            problems.append(f"{key} changed or is missing in the saved campaign metadata")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    airflow_names = r.skill_names(args.skills_dir)
    contexts, queries = load_queries(args.queries, airflow_names)
    if args.query_ids:
        queries = [q for q in queries if q["id"] in args.query_ids]
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    rows_path = out / "runs.jsonl"

    if args.report_only:
        meta = json.loads((out / "meta.json").read_text())
        rows = [json.loads(line) for line in rows_path.read_text().splitlines() if line.strip()]
        ran = set(meta.get("query_ids") or [q["id"] for q in queries])
        queries = [q for q in queries if q["id"] in ran]
        write_report(out, rows, airflow_names, queries, meta["models"], _report_meta(meta))
        print((out / "REPORT.md").read_text())
        return 0

    provenance = {
        "airflow_skills_sha256": r.hash_dir(args.skills_dir),
        "queries_sha256": hashlib.sha256(args.queries.read_bytes()).hexdigest(),
        "fixtures_sha256": {name: r.hash_dir(c["fixture"]) for name, c in contexts.items()},
    }
    done: dict[tuple, dict] = {}
    redo: dict[tuple, dict] = {}
    old_meta: dict = {}
    if args.resume and rows_path.exists():
        old_meta = json.loads((out / "meta.json").read_text()) if (out / "meta.json").exists() else {}
        problems = resume_meta_problems(old_meta, args.runner, models, provenance)
        if problems:
            r.log(f"ABORT: --resume inputs differ from {out}/meta.json: " + "; ".join(problems)
                  + ". Start a new --out directory.")
            return 2
        done, redo = r.load_resume(rows_path, key=trigger_key)

    versions = {c["airflow_version"] or FALLBACK_AIRFLOW_VERSION for c in contexts.values()}
    missing = r.missing_interpreters(versions)
    if missing:
        raise SystemExit("missing interpreters (run evals/harness/setup_envs.sh):\n  " + "\n  ".join(missing))
    claude = args.runner == "claude-code"
    if claude:
        r.require_claude_token()
    skills_sha_before = provenance["airflow_skills_sha256"]
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    args.work_dir = r.work_root() / f"{out.name}-triggers-{stamp}"
    args.work_dir.mkdir(parents=True)
    staged = r.stage_skills("skill", args.repo_skills_dir, args.skills_dir, args.work_dir / "skills")
    repo_names = [n for n in r.skill_names(staged) if n not in airflow_names]
    probe = args.work_dir / "inventory-probe"
    sandbox = not args.no_sandbox and iso.sandbox_available()
    flat = None
    if claude:
        flat = args.work_dir / "skills-flat"
        repo_names = [n for n in cc.flatten_skills(staged, flat) if n not in airflow_names]
        inventory = r.claude_inventory(probe, staged, flat, g.agent_env_python(FALLBACK_AIRFLOW_VERSION), models[0],
                                       sandbox, out)
        problems = cc.check_inventory("skill", inventory, airflow_names, repo_names)
        inv_summary = sorted((s.get("name"), s.get("source")) for s in inventory.get("context_skills") or [])
        n_skills = len(inventory.get("skills") or [])
    else:
        (probe / "ws").mkdir(parents=True)
        r.git(probe / "ws", "init", "-q")
        inventory = r.list_skills(
            r.build_agent_env(probe, probe / "ws", staged, g.agent_env_python(FALLBACK_AIRFLOW_VERSION)),
            probe / "ws")
        problems = r.check_inventory("skill", inventory, staged, airflow_names, repo_names)
        inv_summary = sorted((s.get("name"), s.get("source")) for s in inventory)
        n_skills = len(inventory)
    r.log(f"inventory ({args.runner}): {n_skills} skills; problems={problems or 'none'}")
    if problems:
        r.log("ABORT: skill inventory check failed")
        return 2
    args.ctx = r.AttemptContext(
        out_dir=out, work_dir=args.work_dir, staged_skills=staged,
        altimate_version="" if claude else r.altimate_version(),
        sandbox=sandbox, env_guards=r.make_env_guards(versions),
        run_caps={m: trigger_run_cap(m, args.run_cap_overrides, args.max_run_cost_usd) for m in models},
        runner=args.runner, flat_skills=flat, arm="skill", airflow_names=airflow_names, repo_names=repo_names,
        runner_version=cc.version() if claude else "",
        usage_gate=cc.UsageLimitGate(log=r.log) if claude else None,
        expected_skills=list(inventory.get("skills") or []) if claude else None,
    )
    san.write_json(out / "inventory-skill.json", inventory)
    meta = {
        "run_name": out.name,
        "kind": "triggers",
        "runner": args.runner,
        "models": models,
        "runs_per_query": args.runs,
        "max_turns": args.max_turns,
        "argv": sys.argv,
        "started_at": old_meta.get("started_at") or r.utcnow(),
        "altimate_code_version": args.ctx.altimate_version or None,
        "small_model": None if claude else r.SMALL_MODEL,
        "queries_file": str(args.queries),
        **provenance,
        "query_ids": [q["id"] for q in queries],
        "airflow_skills_dir": str(args.skills_dir),
        "airflow_skill_names": airflow_names,
        "repo_skill_names": repo_names,
        "staged_skills_sha256": r.hash_dir(staged),
        "inventory": inv_summary,
        "isolation": {"sandbox": sandbox, "per_attempt_tmpdir": True, "per_attempt_xdg_data": True,
                      "signals_same_sandbox_only": sandbox},
        "cost_correction": {m: g.cache_correction_applies(m, args.ctx.altimate_version) for m in models},
        "harness_sha256": r.hash_dir(HARNESS_DIR),
        "repo_head": r.repo_head(),
        "host": {"platform": platform.platform(), "python": platform.python_version()},
        "budget": {"cap_usd": args.max_cost_usd, "per_run_cap_usd": args.ctx.run_caps},
    }
    if claude:
        meta.update({"claude_code_version": args.ctx.runner_version,
                     "billing": "subscription (Claude Code OAuth); cost_usd = API-equivalent total_cost_usd"})
        meta["isolation"].update({"claude_config_dir": "fresh per attempt", "claude_env": cc.ISOLATION_ENV,
                                  "strict_mcp_config": True})
    if args.resume:
        meta["resumed_at"] = list(old_meta.get("resumed_at") or []) + ([r.utcnow()] if old_meta else [])
    san.write_json(out / "meta.json", meta)
    if rows_path.exists():
        rows_path.rename(rows_path.with_suffix(f".jsonl.prev-{stamp}"))
    for row in [*done.values(), *redo.values()]:
        san.append_jsonl(rows_path, row)
    budget = r.Budget(args.max_cost_usd)
    budget.spent = sum(float(x.get("cost_usd") or 0) for x in [*done.values(), *redo.values()])
    # Run-major order: when the budget runs out, whole later runs are dropped, not whole queries.
    jobs = [(q, m, i) for i in range(1, args.runs + 1) for q in queries for m in models
            if (q["id"], m, i) not in done]
    r.log(f"{len(jobs)} runs ({len(queries)} queries x {len(models)} models x {args.runs}; {len(done)} already done) "
          f"runner={args.runner} parallel={args.parallel} sandbox={sandbox} caps={args.ctx.run_caps}")
    lock = threading.Lock()
    rows: list[dict] = list(done.values())

    def job(item):
        q, model, idx = item
        row = new_row(q, model, idx)
        prev = redo.get((q["id"], model, idx))
        if prev:  # keep the earlier attempts (and their spend) of a resumed run
            row["attempts"] = [a for a in prev.get("attempts") or [] if not str(a.get("status")).startswith("skipped_")]
        try:
            row = run_one(q, contexts[q["context"]], model, idx, out, staged, args, budget, row)
        except Exception as exc:  # noqa: BLE001 - keep every run accounted for, with its spend
            import traceback

            row["attempts"].append({"status": "harness_error", "reason": f"{type(exc).__name__}: {exc}"[:500],
                                    "fired": [], "cost_usd": 0.0, "launched": False})
            finalize_row(row)
            row["harness_exception"] = traceback.format_exc()[-2000:]
            r.log(f"HARNESS EXCEPTION {q['id']} {model} run-{idx}: {exc}")
        with lock:
            rows.append(row)
            san.append_jsonl(rows_path, row)
        return row

    try:
        with cf.ThreadPoolExecutor(max_workers=max(1, args.parallel)) as ex:
            list(ex.map(job, jobs))
    finally:
        if args.resume:
            r.compact_rows(rows_path, key=trigger_key)
    rows = list({trigger_key(x): x for x in rows}.values())
    skills_sha_after = r.hash_dir(args.skills_dir)
    meta.update({
        "finished_at": r.utcnow(),
        "airflow_skills_sha256_after": skills_sha_after,
        "airflow_skills_unchanged": skills_sha_after == skills_sha_before,
        "status_counts": {s: sum(1 for x in rows if x["status"] == s) for s in sorted({x["status"] for x in rows})},
    })
    meta["isolation"].update({
        "contamination_suspect_runs": sum(1 for x in rows if x.get("contamination_suspect")),
        "kill_command_runs": sum(1 for x in rows if x.get("kill_command")),
        "killed_attempts": sum(x.get("killed_attempts") or 0 for x in rows),
        "agent_env_restores": {v: gd.restores for v, gd in args.ctx.env_guards.items()},
    })
    meta["budget"].update({"spent_usd": round(budget.spent, 4), "stopped_early": budget.stopped})
    rc = 0
    gate = args.ctx.usage_gate
    if gate is not None:
        meta["usage_limit"] = {"stopped": gate.stopped, "paused_s": gate.waited_s, "events": gate.events}
        if gate.stopped:
            rc = 3
            r.log("STOPPED by usage limit; rerun the same command with --resume to continue")
    if args.ctx.abort_reason:
        meta["aborted"] = args.ctx.abort_reason
        rc = 2
    san.write_json(out / "meta.json", meta)
    write_report(out, rows, airflow_names, queries, models, _report_meta(meta))
    r.log(f"done: {len(rows)} runs; spent ${budget.spent:.2f}{' (API-equivalent)' if claude else ''}; "
          f"results in {out}")
    return rc


def trigger_key(row: dict) -> tuple:
    return (row.get("query_id"), row.get("model"), row.get("run"))




def _report_meta(meta: dict) -> dict:
    return {"runs_per_query": meta.get("runs_per_query"), "max_turns": meta.get("max_turns"),
            "airflow_skills_sha256": meta.get("airflow_skills_sha256"),
            "airflow_skills_unchanged": meta.get("airflow_skills_unchanged"),
            "spent_usd": meta.get("budget", {}).get("spent_usd", 0), "cap_usd": meta.get("budget", {}).get("cap_usd", 0)}


if __name__ == "__main__":
    sys.exit(main())
