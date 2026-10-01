"""Grader for authoring-partner-feeds-mapping (Airflow 3.3).

Primary checks: the DAG imports; its task set does not depend on which files
exist at parse time and it uses dynamic task mapping; `airflow dags test` for
days with 0, 1 and 4 partner files succeeds, creates exactly one mapped task
instance per file, writes correct per-partner and summary files (the summary
also on the empty day) and a rerun reproduces the same outputs.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

DAG_ID = "partner_feeds"
FIXTURE_DATA = CASE_DIR / "fixture" / "data"
# Grader-owned drops differ from the sample files and include a partner (wayne) that is not in
# data/partners.json: the set of partners must come from the files, not the registry.
GRADER_DROPS = CASE_DIR / "grader_data" / "partner_drop"
SCENARIOS = {"2026-09-01": 0, "2026-09-02": 1, "2026-09-03": 4}
TOL = 0.05
DAGS_TEST_TIMEOUT_S = 240


def expected(day: str) -> tuple[dict[str, dict], dict]:
    per: dict[str, dict] = {}
    folder = GRADER_DROPS / day
    for p in sorted(folder.glob("*.csv")) if folder.is_dir() else []:
        with p.open(newline="") as fh:
            amounts = [float(r["amount"]) for r in csv.DictReader(fh)]
        per[p.stem] = {"partner": p.stem, "rows": len(amounts), "total_amount": round(sum(amounts), 2)}
    summary = {"files": len(per), "rows": sum(v["rows"] for v in per.values()),
               "total_amount": round(sum(v["total_amount"] for v in per.values()), 2)}
    return per, summary


def close(got: dict | None, want: dict) -> bool:
    if not isinstance(got, dict):
        return False
    for k, v in want.items():
        if k not in got:
            return False
        if isinstance(v, float):
            try:
                if abs(float(got[k]) - v) > TOL:
                    return False
            except (TypeError, ValueError):
                return False
        elif got[k] != v:
            return False
    return True


def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def check_outputs(ws: Path, day: str) -> tuple[bool, bool, str]:
    """(partner files ok, summary ok, detail)."""
    per_want, sum_want = expected(day)
    out = ws / "output" / "partner_feeds" / day
    per_ok = all(close(load_json(out / f"{p}.json"), w) for p, w in per_want.items())
    got_sum = load_json(out / "summary.json")
    sum_ok = close(got_sum, sum_want)
    detail = f"{day}: summary expected {sum_want} got {got_sum}"
    if not per_ok:
        detail += f"; partner files expected {per_want} got " + str(
            {p: load_json(out / f"{p}.json") for p in per_want})
    return per_ok, sum_ok, detail


def mapped_counts(runs: list[dict], day: str) -> dict[str, int]:
    """task_id -> number of expanded (map_index >= 0) task instances in the run for ``day``."""
    counts: dict[str, int] = {}
    for r in runs:
        if not (r.get("logical_date") or "").startswith(day):
            continue
        for key in r["tasks"]:
            if "[" in key:
                tid = key.split("[", 1)[0]
                counts[tid] = counts.get(tid, 0) + 1
    return counts


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    shutil.rmtree(ws / "output", ignore_errors=True)
    shutil.rmtree(ws / "data", ignore_errors=True)
    shutil.copytree(FIXTURE_DATA, ws / "data")
    shutil.rmtree(ws / "data" / "partner_drop")
    shutil.copytree(GRADER_DROPS, ws / "data" / "partner_drop")

    imp = g.import_dags(py, ws)
    dag = imp["dags"].get(DAG_ID)
    grader.primary("DAGs import cleanly", imp["ok"] and not imp["import_errors"],
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items()))
    grader.primary(f"DAG {DAG_ID} exists", dag is not None, f"found: {sorted(imp['dags'])}")
    if dag is None:
        g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
        grader.write(args.out)
        return

    # The task set must not depend on the files present when the file is parsed.
    no_drops = g.copy_workspace(ws)
    shutil.rmtree(no_drops / "data" / "partner_drop", ignore_errors=True)
    more_drops = g.copy_workspace(ws)
    extra = more_drops / "data" / "partner_drop" / "2026-09-05"
    extra.mkdir(parents=True)
    for name in ("zeta", "omega", "sigma"):
        (extra / f"{name}.csv").write_text("order_id,amount\nX-1,10.00\n")
    shapes = {}
    for label, root in (("fixture data", ws), ("no partner_drop dir", no_drops), ("extra files", more_drops)):
        res = imp if root is ws else g.import_dags(py, root)
        d = res["dags"].get(DAG_ID)
        shapes[label] = d["tasks"] if d else f"not loaded: {res['import_errors'] or res['probe_error']}"
    stable = all(v == shapes["fixture data"] for v in shapes.values())
    grader.primary("task set is independent of files present at parse time", stable, json.dumps(shapes))
    mapped = [t for t, d in dag["task_details"].items() if d["mapped"]]
    grader.primary("uses dynamic task mapping", bool(mapped), f"mapped tasks: {mapped}")

    env = g.airflow_env(ws)
    results = {}
    for day in SCENARIOS:
        # A failed task waits out its retry_delay under `dags test`; stop at the first failure.
        results[day] = g.run_dags_test(py, ws, DAG_ID, day, env=env, timeout=DAGS_TEST_TIMEOUT_S)
        if not results[day].ok:
            break
    all_ok = len(results) == len(SCENARIOS) and all(r.ok for r in results.values())
    bad = {d: r for d, r in results.items() if not r.ok}
    grader.primary("airflow dags test succeeds for 0, 1 and N files", all_ok,
                   "" if all_ok else "; ".join(f"{d}: failed tasks {r.failed_tasks()}\n{r.log[-1500:]}"
                                               for d, r in bad.items()))

    runs = results[max(results)].runs
    per_day = {day: mapped_counts(runs, day) for day in SCENARIOS}
    one_per_file = any(
        all(per_day[day].get(t, 0) == n for day, n in SCENARIOS.items()) for t in mapped)
    grader.primary("one mapped task instance per file (0/1/N)", all_ok and one_per_file,
                   f"expected {SCENARIOS}; expanded instances per mapped task: {per_day}")

    outs = {day: check_outputs(ws, day) for day in SCENARIOS}
    grader.primary("per-partner result files are correct",
                   all(o[0] for o in outs.values()), " | ".join(o[2] for o in outs.values() if not o[0]))
    grader.primary("summary is correct, including the day with no files",
                   all(o[1] for o in outs.values()), " | ".join(o[2] for o in outs.values() if not o[1]))

    rerun_day = "2026-09-03"
    again = g.run_dags_test(py, ws, DAG_ID, rerun_day, env=env, timeout=DAGS_TEST_TIMEOUT_S) if all_ok else None
    re_per, re_sum, re_det = check_outputs(ws, rerun_day)
    grader.primary("rerun of a day reproduces the same outputs", bool(again and again.ok) and re_per and re_sum,
                   re_det if again else "skipped: first runs failed")

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
