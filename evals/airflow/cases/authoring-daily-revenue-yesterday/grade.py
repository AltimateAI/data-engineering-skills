"""Grader for authoring-daily-revenue-yesterday (Airflow 3.3).

The grader reproduces the scheduler: it asks the DAG's timetable for the
scheduled run that fires at 03:00 UTC on day D, then executes that run with
exactly the scheduler's logical date and data interval (``dag.test`` with the
timetable's manual-interval inference pinned to the scheduled interval). The
run must write only the file for D-1, with that calendar day's orders.
Works for any timetable choice (cron string, CronDataIntervalTimetable,
CronTriggerTimetable with an interval, ...).
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

DAG_ID = "daily_revenue"
FIXTURE_DATA = CASE_DIR / "fixture" / "data"
# scheduled trigger time -> calendar day that run must report
SCENARIOS = {"2026-09-29T03:00:00+00:00": "2026-09-28", "2026-09-26T03:00:00+00:00": "2026-09-25"}
TOL = 0.011

SCHEDULED_RUN_PROBE = r'''
import pendulum
from airflow.timetables.base import DataInterval
DAG_ID, RUN_AFTER = __ARGS__
dag = get_dag(DAG_ID)
target = pendulum.parse(RUN_AFTER)
runs = scheduled_intervals(dag, target.subtract(days=2), n=4)
info = next((r for r in runs if pendulum.parse(r["run_after"]) == target), None)
if info is None:
    RESULT = {"error": f"the timetable has no run firing at {RUN_AFTER}", "runs": runs}
else:
    start, end = pendulum.parse(info["start"]), pendulum.parse(info["end"])
    # dag.test() derives the interval via infer_manual_data_interval(); pin it
    # to the scheduled interval so the run matches what the scheduler creates.
    cls = type(core_timetable(dag))
    cls.infer_manual_data_interval = lambda self, *, run_after: DataInterval(start, end)
    dr = dag.test(logical_date=start, run_after=target)
    from airflow.models.taskinstance import TaskInstance
    from airflow.utils.session import create_session
    with create_session() as s:
        tis = {ti.task_id: str(getattr(ti.state, "value", ti.state))
               for ti in s.query(TaskInstance).filter(TaskInstance.dag_id == DAG_ID,
                                                     TaskInstance.run_id == dr.run_id)}
    RESULT = {"info": info, "state": str(getattr(dr.state, "value", dr.state)), "tasks": tis,
              "logical_date": dr.logical_date.isoformat() if dr.logical_date else None}
'''


def expected(day: str) -> dict[str, tuple[int, float]]:
    orders: dict[str, int] = defaultdict(int)
    revenue: dict[str, float] = defaultdict(float)
    with (FIXTURE_DATA / "orders.csv").open(newline="") as fh:
        for r in csv.DictReader(fh):
            if r["order_ts"][:10] == day:
                orders[r["store_id"]] += 1
                revenue[r["store_id"]] += float(r["amount"])
    return {s: (orders[s], round(revenue[s], 2)) for s in orders}


def read_output(path: Path) -> dict[str, tuple[int, float]] | str:
    if not path.exists():
        return "missing"
    try:
        with path.open(newline="") as fh:
            return {r["store_id"].strip(): (int(float(r["orders"])), round(float(r["revenue"]), 2))
                    for r in csv.DictReader(fh)}
    except (KeyError, ValueError) as exc:
        return f"unreadable: {exc!r}"


def matches(got, want: dict[str, tuple[int, float]]) -> bool:
    return isinstance(got, dict) and set(got) == set(want) and all(
        got[s][0] == want[s][0] and abs(got[s][1] - want[s][1]) <= TOL for s in want)


def run_scheduled(py: str, ws: Path, env: dict, run_after: str) -> tuple[dict | None, str]:
    code = SCHEDULED_RUN_PROBE.replace("__ARGS__", repr((DAG_ID, run_after)))
    res, proc = g.probe_json(py, code, ws, env=env)
    return res, proc.tail(40)


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    shutil.rmtree(ws / "output", ignore_errors=True)
    shutil.rmtree(ws / "data", ignore_errors=True)
    shutil.copytree(FIXTURE_DATA, ws / "data")

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

    res, proc = g.probe_json(py, f'''
        RESULT = scheduled_intervals(get_dag({DAG_ID!r}), "2026-10-01T00:00:00+00:00", n=3)
    ''', ws)
    stamps = [datetime.fromisoformat(r["run_after"]) for r in (res or [])]
    daily_0300 = len(stamps) == 3 and all(
        s.utcoffset().total_seconds() == 0 and (s.hour, s.minute) == (3, 0) for s in stamps) and all(
        (b - a).total_seconds() == 86400 for a, b in zip(stamps, stamps[1:]))
    grader.primary("scheduled runs fire daily at 03:00 UTC", daily_0300,
                   json.dumps(res) if res is not None else proc.tail(20))

    env = g.airflow_env(ws)
    g.ensure_db(py, env)
    out_dir = ws / "output" / "daily_revenue"
    first_after, first_day = next(iter(SCENARIOS.items()))
    runs_ok, detail, reported_ok = True, [], True
    for i, (run_after, day) in enumerate(SCENARIOS.items()):
        before = set(p.name for p in out_dir.glob("*.csv")) if out_dir.exists() else set()
        res, tail = run_scheduled(py, ws, env, run_after)
        ok = bool(res) and res.get("state") == "success" and bool(res.get("tasks"))
        runs_ok &= ok
        written = (set(p.name for p in out_dir.glob("*.csv")) if out_dir.exists() else set()) - before
        got = read_output(out_dir / f"{day}.csv")
        good = ok and written == {f"{day}.csv"} and matches(got, expected(day))
        reported_ok &= good
        detail.append(f"run firing {run_after}: state={res.get('state') if res else None} "
                      f"logical_date={res.get('logical_date') if res else None} new files={sorted(written)} "
                      f"expected {day}.csv={expected(day)} got={got}"
                      + ("" if res else f"\nprobe output: {tail}")
                      + (f" error={res.get('error')} runs={res.get('runs')}" if res and res.get("error") else ""))
    grader.primary("scheduled runs execute successfully", runs_ok, "\n".join(detail))
    grader.primary("the 03:00 run on day D reports calendar day D-1 (and only that day)", reported_ok,
                   "\n".join(detail))

    res, tail = run_scheduled(py, ws, env, first_after)
    again = read_output(out_dir / f"{first_day}.csv")
    grader.primary("rerun of a scheduled run reproduces the same file",
                   bool(res) and res.get("state") == "success" and matches(again, expected(first_day)),
                   f"state={res.get('state') if res else tail}; got={again}")

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
