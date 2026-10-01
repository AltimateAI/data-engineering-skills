"""Grader for scheduling-backfill-pageviews (Airflow 3.3).

The user wants the scheduler to backfill every day since 2026-09-01 on its own
when the DAG is unpaused, one writer at a time, with re-runs that never double
count. "Now" is pinned to 2026-09-30 12:00 UTC (exports exist for 09-01..09-29).

Primary checks:
- DAG attributes: catchup enabled; at most one writer at a time across runs
  (max_active_runs == 1, or a single-task DAG with max_active_tis_per_dag == 1;
  max_active_tasks alone is per run on 3.x and does not serialise catchup);
  start_date is a fixed value (parsing under a clock shifted by 400 days
  yields the same start_date).
- Backfill: every run the timetable creates from start_date up to "now" is
  executed in order, as the scheduler would create it (own logical date and
  data interval, via ``dag.test``), against an empty warehouse. All runs must
  succeed and the warehouse must hold exactly the correct rows for 09-01..09-29
  and nothing else.
- Timing: each run only loads days whose export had landed (D+1 01:00 UTC per
  the fixture README) at the run's run_after. The simulation has every file
  already, so this catches schedules that would skip or fail in production.
- Re-run: the day 09-15 is corrupted (duplicated rows, stale counts) and the
  run that loaded it is executed again; it must repair 09-15 and leave every
  other day untouched.
- A plain ``airflow dags test`` succeeds.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

DAG_ID = "pageviews_daily"
NOW = "2026-09-30T12:00:00+00:00"
FIRST_DAY, LAST_DAY = date(2026, 9, 1), date(2026, 9, 29)
REPAIR_DAY = "2026-09-15"
MAX_RUNS = 40  # 29 days are expected; anything far above means start_date is too early
WAREHOUSE_REL = Path("warehouse") / "web.duckdb"
EXPORT_LANDS_HOUR_UTC = 1  # fixture README: each day's export is written at about 01:00 UTC the next morning
EXPECTED_DAYS = [(FIRST_DAY + timedelta(days=i)).isoformat() for i in range((LAST_DAY - FIRST_DAY).days + 1)]


def expected_rows() -> dict[str, dict[str, tuple[int, int]]]:
    """{day: {page: (views, unique_visitors)}} from the pristine fixture exports."""
    out: dict[str, dict[str, tuple[int, int]]] = {}
    for f in sorted((CASE_DIR / "fixture" / "data" / "pageviews").glob("*.csv")):
        views: dict[str, int] = defaultdict(int)
        visitors: dict[str, set] = defaultdict(set)
        with f.open(newline="") as fh:
            for row in csv.DictReader(fh):
                views[row["page"]] += 1
                visitors[row["page"]].add(row["visitor_id"])
        out[f.stem] = {p: (views[p], len(visitors[p])) for p in views}
    return out


def check_warehouse(rows: list | None, exp: dict) -> tuple[bool, str]:
    if rows is None:
        return False, "daily_pageviews unreadable"
    by_day: dict[str, list] = defaultdict(list)
    for d, page, views, uniq in rows:
        by_day[d].append((page, views, uniq))
    problems = []
    extra = sorted(set(by_day) - set(EXPECTED_DAYS))
    if extra:
        problems.append(f"rows for days outside 09-01..09-29: {extra[:5]}{'...' if len(extra) > 5 else ''}")
    missing = [d for d in EXPECTED_DAYS if d not in by_day]
    if missing:
        problems.append(f"missing days {missing[:8]}{'...' if len(missing) > 8 else ''} ({len(missing)} total)")
    wrong = []
    for d in EXPECTED_DAYS:
        if d not in by_day:
            continue
        pages = [p for p, _, _ in by_day[d]]
        got = {p: (v, u) for p, v, u in by_day[d]}
        if len(pages) != len(set(pages)) or got != exp[d]:
            wrong.append(d)
    if wrong:
        problems.append(f"wrong or duplicated rows for {wrong[:8]}")
    return not problems, "; ".join(problems)


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------

_ATTR_CODE = r'''
dag = get_dag(DAG_ID)
RESULT = {"catchup": dag.catchup, "max_active_runs": dag.max_active_runs,
          "max_active_tasks": getattr(dag, "max_active_tasks", None),
          "task_limits": {t.task_id: getattr(t, "max_active_tis_per_dag", None) for t in dag.tasks},
          "start_date": str(dag.start_date), "end_date": str(dag.end_date)}
'''


def single_writer(attrs: dict) -> tuple[bool, str]:
    """At most one task instance of the DAG can write the DuckDB file at a time, across runs.

    ``max_active_runs == 1`` serialises runs. A single-task DAG whose task has
    ``max_active_tis_per_dag == 1`` is serialised across runs too. On Airflow 3.x
    ``max_active_tasks`` is enforced per DAG run, so on its own it still lets
    catchup run up to ``max_active_runs`` writers in parallel. A pool is not
    accepted: it only exists once someone creates it in the metadata DB.
    """
    limits = attrs.get("task_limits") or {}
    ok = attrs["max_active_runs"] == 1 or (len(limits) == 1 and list(limits.values()) == [1])
    return ok, (f"max_active_runs={attrs['max_active_runs']}, max_active_tasks={attrs['max_active_tasks']} "
                f"(per run on 3.x), task max_active_tis_per_dag={limits}")

# Parse the DAG under a clock shifted forward by 400 days.
_SHIFTED_CLOCK_CODE = r'''
import datetime as _dt
import pendulum
SHIFT = _dt.timedelta(days=400)
_Real, _RealDate = _dt.datetime, _dt.date

# Like freezegun: isinstance() against the replacement classes still accepts real instances.
class _DTMeta(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _Real)
    def __subclasscheck__(cls, sub):
        return issubclass(sub, _Real)

class _DateMeta(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _RealDate)
    def __subclasscheck__(cls, sub):
        return issubclass(sub, _RealDate)

class _ShiftedDateTime(_Real, metaclass=_DTMeta):
    @classmethod
    def now(cls, tz=None):
        return _Real.now(tz) + SHIFT
    @classmethod
    def utcnow(cls):
        return _Real.utcnow() + SHIFT
    @classmethod
    def today(cls):
        return _Real.today() + SHIFT

class _ShiftedDate(_RealDate, metaclass=_DateMeta):
    @classmethod
    def today(cls):
        return _RealDate.fromordinal(_Real.today().toordinal() + 400)

_dt.datetime = _ShiftedDateTime
_dt.date = _ShiftedDate
_pnow = pendulum.now
pendulum.now = lambda tz="local": _pnow(tz).add(days=400)
pendulum.today = lambda tz="local": _pnow(tz).add(days=400).start_of("day")
pendulum.yesterday = lambda tz="local": _pnow(tz).add(days=399).start_of("day")
for modname in ("airflow.utils.timezone", "airflow.sdk.timezone"):
    try:
        mod = __import__(modname, fromlist=["utcnow"])
        _u = mod.utcnow
        mod.utcnow = lambda _u=_u: _u() + SHIFT
    except Exception:
        pass
dag = get_dag(DAG_ID)
RESULT = {"start_date": str(dag.start_date)}
'''

# Execute scheduled runs (the timetable's own logical date and data interval).
# MODE "backfill": every run from start_date with run_after <= NOW, recording the
# days each run added. MODE "single": only run number RUN_INDEX of that sequence.
_RUNS_CODE = r'''
import duckdb, pathlib, pendulum
from airflow.timetables.base import DataInterval, TimeRestriction
dag = get_dag(DAG_ID)
tt = core_timetable(dag)
for t in dag.tasks:
    t.retries = 0  # a failed run must fail fast instead of waiting for retry_delay
wh = pathlib.Path(WAREHOUSE)
latest = pendulum.parse(NOW)
infos, last = [], None
for _ in range(MAX_RUNS + 1):
    info = tt.next_dagrun_info(last_automated_data_interval=last,
                               restriction=TimeRestriction(earliest=dag.start_date, latest=dag.end_date, catchup=True))
    if info is None or info.run_after > latest:
        break
    infos.append(info)
    last = info.data_interval

def days():
    if not wh.exists():
        return set()
    con = duckdb.connect(str(wh), read_only=True)
    try:
        return {str(r[0]) for r in con.execute("SELECT DISTINCT CAST(view_date AS VARCHAR) FROM daily_pageviews").fetchall()}
    except Exception:
        return set()
    finally:
        con.close()

out = {"n_runs": len(infos),
       "first": [str(infos[0].logical_date), str(infos[0].data_interval.start), str(infos[0].run_after)] if infos else None,
       "runs": []}
if len(infos) <= MAX_RUNS:
    todo = list(enumerate(infos)) if MODE == "backfill" else [(RUN_INDEX, infos[RUN_INDEX])]
    failures = 0
    for i, info in todo:
        di = info.data_interval
        patched = lambda self, run_after, di=di: DataInterval(di.start, di.end)
        type(tt).infer_manual_data_interval = patched
        type(dag.timetable).infer_manual_data_interval = patched
        before = days()
        rec = {"i": i, "logical_date": str(info.logical_date), "interval": [str(di.start), str(di.end)],
               "run_after": pendulum.instance(info.run_after).in_timezone("UTC").isoformat()}
        try:
            dr = dag.test(logical_date=info.logical_date)
            rec["state"] = str(getattr(dr.state, "value", dr.state)) if dr is not None else None
        except Exception as exc:
            rec["state"] = "error: " + repr(exc)[:300]
        rec["new_days"] = sorted(days() - before)
        out["runs"].append(rec)
        if rec["state"] != "success":
            failures += 1
            if failures >= 3:
                out["aborted"] = "stopped after 3 failed runs"
                break
RESULT = out
'''

_READ_CODE = r'''
import duckdb, json, sys
con = duckdb.connect(sys.argv[1], read_only=True)
rows = con.execute("SELECT CAST(view_date AS VARCHAR), page, views, unique_visitors FROM daily_pageviews").fetchall()
print("__WH__" + json.dumps([[str(a), str(b), int(c), int(d)] for a, b, c, d in rows]))
'''

_CORRUPT_CODE = r'''
import duckdb, sys
con = duckdb.connect(sys.argv[1])
day = sys.argv[2]
# A crashed or doubled attempt: the day's rows are duplicated and one count is stale.
con.execute("INSERT INTO daily_pageviews SELECT * FROM daily_pageviews WHERE CAST(view_date AS VARCHAR) = ?", [day])
con.execute("UPDATE daily_pageviews SET views = views + 7 WHERE CAST(view_date AS VARCHAR) = ? AND page = '/'", [day])
con.close()
print("CORRUPTED")
'''


def loads_after_export_lands(runs: list[dict]) -> tuple[bool, str]:
    """Every run loads only days whose export had landed (next day 01:00 UTC) when the run starts.

    Under catchup every export already exists, so a run scheduled before its
    day's export lands still succeeds in the simulation; in production it would
    fail, or skip and never load the day."""
    loaded = [(r["run_after"], d) for r in runs if r.get("state") == "success" for d in r.get("new_days", [])]
    if not loaded:
        return False, "no run loaded any day"
    early = []
    for run_after, d in loaded:
        lands = datetime.combine(date.fromisoformat(d) + timedelta(days=1), time(EXPORT_LANDS_HOUR_UTC),
                                 tzinfo=timezone.utc)
        if datetime.fromisoformat(run_after) < lands:
            early.append(f"{d} loaded by the run at {run_after}")
    return not early, (f"export for day D lands at D+1 {EXPORT_LANDS_HOUR_UTC:02d}:00 UTC; "
                       + ("; ".join(early[:5]) if early else f"{len(loaded)} day loads checked"))


def migrated_env(py: str, ws: Path) -> dict:
    env = g.airflow_env(ws)
    db = g.ensure_db(py, env)
    if not db.ok:
        raise RuntimeError("airflow db migrate failed: " + db.tail(20))
    return env


def execute_runs(py: str, ws: Path, mode: str, run_index: int = 0) -> tuple[dict | None, str]:
    code = (f"DAG_ID = {DAG_ID!r}\nNOW = {NOW!r}\nMAX_RUNS = {MAX_RUNS}\nMODE = {mode!r}\n"
            f"RUN_INDEX = {run_index}\nWAREHOUSE = {str(ws / WAREHOUSE_REL)!r}\n" + _RUNS_CODE)
    res, proc = g.probe_json(py, code, ws, env=migrated_env(py, ws), timeout=900)
    return res, proc.tail(40)


def read_rows(py: str, ws: Path) -> list | None:
    db = ws / WAREHOUSE_REL
    if not db.exists():
        return None
    res = g.run_cmd([py, "-c", _READ_CODE, str(db)], env=g.scrubbed_environ(), timeout=120)
    for line in res.stdout.splitlines():
        if line.startswith("__WH__"):
            return json.loads(line[6:])
    return None


def main() -> None:
    args = g.parse_args()
    ws, py = Path(args.workspace), sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)
    exp = expected_rows()

    imp = g.import_dags(py, ws)
    dag = imp["dags"].get(DAG_ID)
    grader.primary("DAGs import cleanly", imp["ok"] and not imp["import_errors"],
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items()))
    grader.primary(f"DAG {DAG_ID} exists", dag is not None, f"found: {sorted(imp['dags'])}")

    if dag is not None:
        attrs, proc = g.probe_json(py, f"DAG_ID = {DAG_ID!r}\n" + _ATTR_CODE, ws)
        if attrs is None:
            grader.primary("catchup enabled", False, "attribute probe failed: " + proc.tail(20))
            grader.primary("one writer at a time", False, "attribute probe failed")
        else:
            grader.primary("catchup enabled", attrs["catchup"] is True, f"catchup={attrs['catchup']!r}")
            grader.primary("one writer at a time", *single_writer(attrs))
            shifted, proc = g.probe_json(py, f"DAG_ID = {DAG_ID!r}\n" + _SHIFTED_CLOCK_CODE, ws)
            if shifted is None:
                grader.primary("start_date is fixed, not computed from the clock", False,
                               "shifted-clock parse failed: " + proc.tail(20))
            else:
                grader.primary("start_date is fixed, not computed from the clock",
                               shifted["start_date"] == attrs["start_date"],
                               f"start_date {attrs['start_date']}; with the clock +400 days: {shifted['start_date']}")

        # Backfill from an empty warehouse, exactly as the scheduler would create the runs.
        shutil.rmtree(ws / "warehouse", ignore_errors=True)
        res, log = execute_runs(py, ws, "backfill")
        backfill_ok = False
        if res is None:
            grader.primary("catchup backfills exactly 09-01..09-29", False, "run probe crashed: " + log)
        elif res["n_runs"] > MAX_RUNS:
            grader.primary("catchup backfills exactly 09-01..09-29", False,
                           f"the scheduler would create more than {MAX_RUNS} runs up to {NOW} "
                           f"(first run {res['first']}); start_date is before the data")
        else:
            failed = [(r["logical_date"], r["state"]) for r in res["runs"] if r["state"] != "success"]
            passed, detail = check_warehouse(read_rows(py, ws), exp)
            backfill_ok = not failed and passed and not res.get("aborted")
            grader.primary("catchup backfills exactly 09-01..09-29", backfill_ok,
                           f"{res['n_runs']} runs, first {res['first']}; "
                           + (f"failed runs {failed[:5]}; " if failed else "") + (res.get("aborted") or "") + detail)

        runs = res.get("runs", []) if isinstance(res, dict) else []
        grader.primary("each run loads a day whose export has already landed", *loads_after_export_lands(runs))

        # Corrupt REPAIR_DAY, re-run the run that loaded it.
        idx = next((r["i"] for r in runs if r.get("new_days") == [REPAIR_DAY]), None)
        db = ws / WAREHOUSE_REL
        if not backfill_ok or idx is None or not db.exists():
            grader.primary("re-running a day repairs it and keeps other days", False,
                           f"needs a clean backfill in which one run loaded {REPAIR_DAY} (run index {idx})")
        else:
            corrupt = g.run_cmd([py, "-c", _CORRUPT_CODE, str(db), REPAIR_DAY], env=g.scrubbed_environ(), timeout=120)
            rerun, log = execute_runs(py, ws, "single", idx) if corrupt.ok else (None, corrupt.tail(10))
            states = [r["state"] for r in rerun["runs"]] if rerun else []
            passed, detail = check_warehouse(read_rows(py, ws), exp)
            grader.primary("re-running a day repairs it and keeps other days",
                           states == ["success"] and passed,
                           f"re-run states {states}; {detail}" if rerun else "re-run failed: " + log)

        # Plain `airflow dags test`.
        scratch = g.copy_workspace(ws)
        shutil.rmtree(scratch / "warehouse", ignore_errors=True)
        manual = g.run_dags_test(py, scratch, DAG_ID, "2026-09-15", env=g.airflow_env(scratch))
        grader.primary("airflow dags test succeeds", manual.ok,
                       "" if manual.ok else f"failed tasks {manual.failed_tasks()}: {manual.log[-2500:]}")

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
