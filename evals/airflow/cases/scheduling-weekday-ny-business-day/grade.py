"""Grader for scheduling-weekday-ny-business-day (Airflow 3.3).

1. Schedule: the DAG's own timetable must produce runs at exactly 06:00
   America/New_York on weekdays only, across both 2026 US DST switches.
2. Semantics: the scheduled runs for Mon 09 Mar, Tue 10 Mar and Mon 02 Nov are
   executed the way the scheduler would create them (the timetable's logical
   date and data interval, via ``dag.test``) and must write exactly the report
   for the previous business day, with correct per-desk totals.
3. A plain ``airflow dags test`` succeeds.
"""

from __future__ import annotations

import csv
import io
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

DAG_ID = "fx_pnl_report"
NY = ZoneInfo("America/New_York")
# Windows around DST start (Sun 2026-03-08) and DST end (Sun 2026-11-01), NY dates [start, end).
WINDOWS = [(date(2026, 3, 4), date(2026, 3, 12)), (date(2026, 10, 28), date(2026, 11, 5))]
# Run day (NY) -> business day its report must cover.
RUN_SCENARIOS = [
    (date(2026, 3, 9), date(2026, 3, 6), "Monday run after DST starts reports Friday"),
    (date(2026, 3, 10), date(2026, 3, 9), "Tuesday run reports Monday"),
    (date(2026, 11, 2), date(2026, 10, 30), "Monday run after DST ends reports Friday"),
]


def ny_midnight_utc(d: date) -> str:
    return datetime(d.year, d.month, d.day, tzinfo=NY).astimezone(timezone.utc).isoformat()


def expected_run_afters(start: date, end: date) -> list[str]:
    out, d = [], start
    while d < end:
        if d.weekday() < 5:
            out.append(datetime(d.year, d.month, d.day, 6, tzinfo=NY).astimezone(timezone.utc).isoformat())
        d += timedelta(days=1)
    return out


def expected_report(trade_date: str) -> dict[str, tuple[int, float, float]]:
    totals: dict[str, list] = defaultdict(lambda: [0, 0.0, 0.0])
    with (CASE_DIR / "fixture" / "data" / "fx_trades.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["trade_date"] == trade_date:
                t = totals[row["desk"]]
                t[0] += 1
                t[1] += float(row["notional_usd"])
                t[2] += float(row["pnl_usd"])
    return {k: (v[0], round(v[1], 2), round(v[2], 2)) for k, v in totals.items()}


def compare_report(text: str, want: dict) -> str:
    """'' when the CSV text matches ``want`` (numeric tolerance), else a reason."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or [c.strip() for c in rows[0]] != ["desk", "trades", "notional_usd", "pnl_usd"]:
        return f"unexpected header {rows[:1]}"
    got = {}
    try:
        for r in rows[1:]:
            if not r:
                continue
            got[r[0]] = (int(float(r[1])), float(r[2]), float(r[3]))
    except (ValueError, IndexError) as exc:
        return f"unparseable row: {exc}"
    if set(got) != set(want):
        return f"desks {sorted(got)} != {sorted(want)}"
    bad = [k for k in want if got[k][0] != want[k][0] or abs(got[k][1] - want[k][1]) > 0.01
           or abs(got[k][2] - want[k][2]) > 0.01]
    return f"wrong totals for {bad}: got {[got[k] for k in bad]}, want {[want[k] for k in bad]}" if bad else ""


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------

_SCHEDULE_CODE = r'''
import pendulum
from airflow.timetables.base import TimeRestriction
dag = get_dag(DAG_ID)
tt = core_timetable(dag)
out = []
for start, end in WINDOWS:
    lo, hi = pendulum.parse(start), pendulum.parse(end)
    last, runs = None, []
    for _ in range(500):
        info = tt.next_dagrun_info(last_automated_data_interval=last,
                                   restriction=TimeRestriction(earliest=lo.subtract(days=7), latest=None, catchup=True))
        if info is None or info.run_after >= hi:
            break
        last = info.data_interval
        if info.run_after >= lo:
            runs.append(pendulum.instance(info.run_after).in_timezone("UTC").isoformat())
    out.append(runs)
RESULT = {"runs": out, "timetable": type(dag.timetable).__name__}
'''

# Executes the scheduled run whose run_after falls on each NY day in RUN_DAYS,
# with that run's own logical date and data interval, and records the reports
# it wrote (the reports dir is emptied before every run).
_RUNS_CODE = r'''
import pathlib, shutil, pendulum
from airflow.timetables.base import DataInterval, TimeRestriction
dag = get_dag(DAG_ID)
tt = core_timetable(dag)
reports = pathlib.Path("reports")
floor = pendulum.datetime(2026, 1, 1, tz="UTC")
if dag.start_date is not None and dag.start_date > floor:
    # A later start_date is not wrong for this request; let the historical runs execute.
    dag.start_date = floor
    for t in dag.tasks:
        if t.start_date is not None and t.start_date > floor:
            t.start_date = floor
out = []
for run_day, lo, hi in RUN_DAYS:
    lo, hi = pendulum.parse(lo), pendulum.parse(hi)
    last, info = None, None
    for _ in range(500):
        nxt = tt.next_dagrun_info(last_automated_data_interval=last,
                                  restriction=TimeRestriction(earliest=lo.subtract(days=7), latest=None, catchup=True))
        if nxt is None or nxt.run_after >= hi:
            break
        if nxt.run_after >= lo:
            info = nxt
            break
        last = nxt.data_interval
    if info is None:
        out.append({"run_day": run_day, "error": "no scheduled run on this New York day"})
        continue
    di = info.data_interval
    patched = lambda self, run_after, di=di: DataInterval(di.start, di.end)
    type(tt).infer_manual_data_interval = patched
    type(dag.timetable).infer_manual_data_interval = patched
    shutil.rmtree(reports, ignore_errors=True)
    rec = {"run_day": run_day, "logical_date": str(info.logical_date), "interval": [str(di.start), str(di.end)],
           "run_after": str(info.run_after)}
    try:
        dr = dag.test(logical_date=info.logical_date)
        rec["state"] = str(getattr(dr.state, "value", dr.state)) if dr is not None else None
        tis = dr.get_task_instances() if dr is not None else []
        rec["tasks"] = {ti.task_id: str(getattr(ti.state, "value", ti.state)) for ti in tis}
    except Exception as exc:
        rec["state"] = "error: " + repr(exc)[:500]
    rec["files"] = {p.name: p.read_text() for p in sorted(reports.glob("*.csv"))} if reports.exists() else {}
    out.append(rec)
shutil.rmtree(reports, ignore_errors=True)
RESULT = out
'''


def main() -> None:
    args = g.parse_args()
    ws, py = Path(args.workspace), sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    imp = g.import_dags(py, ws)
    dag = imp["dags"].get(DAG_ID)
    grader.primary("DAGs import cleanly", imp["ok"] and not imp["import_errors"],
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items()))
    grader.primary(f"DAG {DAG_ID} exists", dag is not None, f"found: {sorted(imp['dags'])}")

    if dag is not None:
        # 1. Schedule across both DST switches.
        windows = [(ny_midnight_utc(a), ny_midnight_utc(b)) for a, b in WINDOWS]
        res, proc = g.probe_json(py, f"DAG_ID = {DAG_ID!r}\nWINDOWS = {windows!r}\n" + _SCHEDULE_CODE, ws)
        want = [expected_run_afters(a, b) for a, b in WINDOWS]
        if res is None:
            grader.primary("runs at 06:00 New York on weekdays only, across DST", False,
                           "timetable probe failed: " + proc.tail(20))
        else:
            got = res["runs"]
            grader.primary("runs at 06:00 New York on weekdays only, across DST", got == want,
                           f"timetable {res['timetable']}; run_after (UTC) got {got}, want {want}")

        # 2. Scheduled runs report the previous business day.
        run_days = [(d.isoformat(), ny_midnight_utc(d), ny_midnight_utc(d + timedelta(days=1)))
                    for d, _, _ in RUN_SCENARIOS]
        scratch = g.copy_workspace(ws)
        runs, proc = g.probe_json(py, f"DAG_ID = {DAG_ID!r}\nRUN_DAYS = {run_days!r}\n" + _RUNS_CODE,
                                  scratch, env=_migrated_env(py, scratch))
        by_day = {r["run_day"]: r for r in runs} if isinstance(runs, list) else {}
        for run_day, report_day, label in RUN_SCENARIOS:
            rec = by_day.get(run_day.isoformat())
            if rec is None:
                grader.primary(label, False, "run probe failed: " + proc.tail(30))
                continue
            if "error" in rec:
                grader.primary(label, False, rec["error"])
                continue
            name = f"fx_pnl_{report_day.isoformat()}.csv"
            problems = []
            if rec.get("state") != "success":
                problems.append(f"run state {rec.get('state')} tasks {rec.get('tasks')}")
            if sorted(rec["files"]) != [name]:
                problems.append(f"reports written {sorted(rec['files'])}, want [{name}]")
            elif (why := compare_report(rec["files"][name], expected_report(report_day.isoformat()))):
                problems.append(why)
            grader.primary(label, not problems,
                           f"logical_date {rec['logical_date']} interval {rec['interval']}; " + "; ".join(problems))

        # 3. Plain `airflow dags test`.
        scratch = g.copy_workspace(ws)
        manual = g.run_dags_test(py, scratch, DAG_ID, "2026-03-10", env=g.airflow_env(scratch))
        grader.primary("airflow dags test succeeds", manual.ok,
                       "" if manual.ok else f"failed tasks {manual.failed_tasks()}: {manual.log[-2500:]}")

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


def _migrated_env(py: str, ws: Path) -> dict:
    env = g.airflow_env(ws)
    db = g.ensure_db(py, env)
    if not db.ok:
        raise RuntimeError("airflow db migrate failed: " + db.tail(20))
    return env


if __name__ == "__main__":
    main()
