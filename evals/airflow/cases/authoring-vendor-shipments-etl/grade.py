"""Grader for authoring-vendor-shipments-etl (Airflow 3.3).

Primary checks: the DAG imports (with no Variables defined), touches no
Variable/Connection/metadata DB while parsing, has sensor -> load -> bash
ordering, the sensor frees its worker slot (reschedule or deferrable) and has
an explicit timeout of at most a day, the DAG runs daily at 06:00 UTC without catchup,
`airflow dags test` loads the file named by the `vendor_landing_dir` Variable
into DuckDB, publishes the report and is idempotent on a rerun, and on a day
whose file is missing nothing downstream of the sensor starts.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

DAG_ID = "vendor_shipments"
DAY, NEIGHBOUR = "2026-09-29", "2026-09-28"
LANDING = CASE_DIR / "grader_data" / "landing"
MAX_SENSOR_TIMEOUT_S = 24 * 3600
DAGS_TEST_TIMEOUT_S = 240  # a sensor looking in the wrong place waits until this kills it
MISSING_DAY = "2026-09-27"  # no landing file for this day
GATE_WINDOW_S = 150
NOT_STARTED = {"None", "none", "scheduled", "upstream_failed", "removed"}
BASH_TYPES = ("BashOperator", "_BashDecoratedOperator")

# Parse the DAG folder with Variable/Connection lookups booby-trapped and the
# metadata DB pointed at a path that cannot exist.
PARSE_GUARD_PROBE = r'''
CALLS = []
def _trap(label):
    def fn(*a, **k):
        CALLS.append(label)
        raise RuntimeError(f"parse-time {label} is not allowed")
    return fn
def _patch(modname, clsname, attr, label):
    try:
        mod = __import__(modname, fromlist=[clsname])
        cls = getattr(mod, clsname)
    except Exception:
        return
    trap = _trap(label)
    setattr(cls, attr, classmethod(lambda cls, *a, **k: trap(*a, **k)))
for _m, _c, _a, _l in [
    ("airflow.sdk.definitions.variable", "Variable", "get", "Variable.get"),
    ("airflow.models.variable", "Variable", "get", "Variable.get"),
    ("airflow.sdk.definitions.connection", "Connection", "get", "Connection.get"),
    ("airflow.models.connection", "Connection", "get_connection_from_secrets", "Connection lookup"),
    ("airflow.sdk.bases.hook", "BaseHook", "get_connection", "BaseHook.get_connection"),
    ("airflow.hooks.base", "BaseHook", "get_connection", "BaseHook.get_connection"),
]:
    _patch(_m, _c, _a, _l)
bag = dagbag()
RESULT = {"calls": CALLS, "dags": sorted(bag.dags),
          "errors": {k: v.strip().splitlines()[-1] for k, v in bag.import_errors.items()}}
'''

SENSOR_PROBE = r'''
from datetime import timedelta
from airflow.sdk import BaseSensorOperator
dag = get_dag("vendor_shipments")
sensors = []
for t in dag.tasks:
    if isinstance(t, BaseSensorOperator):
        to = t.timeout
        to = to.total_seconds() if isinstance(to, timedelta) else float(to)
        sensors.append({"task_id": t.task_id, "class": type(t).__name__, "mode": t.mode,
                        "deferrable": bool(getattr(t, "deferrable", False) or getattr(t, "start_from_trigger", False)),
                        "timeout_s": to})
RESULT = {"sensors": sensors,
          "runs": scheduled_intervals(dag, "2026-10-01T00:00:00+00:00", n=3)}
'''

TABLE_PROBE = r'''
import duckdb, os
path = os.path.join(os.getcwd(), "warehouse", "analytics.duckdb")
if not os.path.exists(path):
    RESULT = {"error": "warehouse/analytics.duckdb was not created"}
else:
    with duckdb.connect(path, read_only=True) as con:
        tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()]
        if "vendor_shipments" not in tables:
            RESULT = {"error": f"no vendor_shipments table; tables: {tables}"}
        else:
            rows = con.execute("SELECT CAST(CAST(ship_date AS DATE) AS VARCHAR), CAST(shipment_id AS VARCHAR) "
                               "FROM vendor_shipments").fetchall()
            RESULT = {"rows": rows}
'''


def landing_rows(day: str) -> list[dict]:
    with (LANDING / f"shipments_{day}.csv").open(newline="") as fh:
        return list(csv.DictReader(fh))


def expected_report(day: str) -> dict[str, tuple[int, float]]:
    count: Counter[str] = Counter()
    weight: dict[str, float] = defaultdict(float)
    for r in landing_rows(day):
        count[r["carrier"]] += 1
        weight[r["carrier"]] += float(r["weight_kg"])
    return {c: (count[c], round(weight[c], 2)) for c in count}


def read_report(ws: Path, day: str) -> dict[str, tuple[int, float]] | None:
    path = ws / "reports" / f"shipments_{day}.csv"
    if not path.exists():
        return None
    with path.open(newline="") as fh:
        return {r["carrier"]: (int(r["shipments"]), round(float(r["total_weight_kg"]), 2))
                for r in csv.DictReader(fh)}


def ancestors(deps: list[list[str]], node: str) -> set[str]:
    ups: dict[str, set[str]] = defaultdict(set)
    for u, d in deps:
        ups[d].add(u)
    seen: set[str] = set()
    stack = [node]
    while stack:
        for u in ups[stack.pop()]:
            if u not in seen:
                seen.add(u)
                stack.append(u)
    return seen


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    # 1. Import with no Variables or Connections defined.
    imp = g.import_dags(py, ws)
    dag = imp["dags"].get(DAG_ID)
    grader.primary("DAGs import cleanly with no Variables defined", imp["ok"] and not imp["import_errors"],
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items()))
    grader.primary(f"DAG {DAG_ID} exists", dag is not None, f"found: {sorted(imp['dags'])}")

    # 2. No Variable / Connection / metadata-DB access while parsing.
    poisoned = g.airflow_env(ws, extra={
        "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN": "sqlite:////nonexistent-eval-dir/poisoned.db"})
    guard, proc = g.probe_json(py, PARSE_GUARD_PROBE, ws, env=poisoned)
    parse_ok = bool(guard) and not guard["calls"] and DAG_ID in guard["dags"] and not guard["errors"]
    grader.primary("no Variable/Connection/metadata-DB access at parse time", parse_ok,
                   json.dumps(guard) if guard else proc.tail(30))

    if dag is None:
        g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
        grader.write(args.out)
        return

    # 3. Task graph: sensor -> python load -> bash report.
    details, deps = dag["task_details"], dag["deps"]
    probe, proc = g.probe_json(py, SENSOR_PROBE, ws)
    sensors = (probe or {}).get("sensors", [])
    sensor_ids = {s["task_id"] for s in sensors}
    bash_ids = [t for t, d in details.items() if d["task_type"] in BASH_TYPES]
    graph_ok, graph_detail = False, f"sensors={sorted(sensor_ids)} bash={bash_ids} deps={deps}"
    for b in bash_ids:
        ups = ancestors(deps, b)
        # The load step may itself be a bash task (e.g. `python scripts/load.py`).
        middle = [t for t in ups - sensor_ids if sensor_ids & ancestors(deps, t)]
        if sensor_ids & ups and middle:
            graph_ok = True
            graph_detail = f"sensor(s) {sorted(sensor_ids & ups)} -> {middle} -> {b}"
            break
    grader.primary("task graph is wait-for-file -> load -> bash report", graph_ok, graph_detail)

    # 4. Sensor does not hold a worker slot and gives up within a day.
    slot_ok = bool(sensors) and all(s["mode"] == "reschedule" or s["deferrable"] for s in sensors)
    grader.primary("file sensor is reschedule-mode or deferrable", slot_ok,
                   json.dumps(sensors) if probe else proc.tail(30))
    timeout_ok = bool(sensors) and all(0 < s["timeout_s"] <= MAX_SENSOR_TIMEOUT_S for s in sensors)
    grader.primary("file sensor has an explicit timeout of at most 24h", timeout_ok, json.dumps(sensors))

    # 5. Schedule: one run per day, no catchup.
    runs = (probe or {}).get("runs", [])
    daily = len(runs) == 3 and all(
        g_delta == 86400 for g_delta in _deltas([r["run_after"] for r in runs])) and all(
        _utc_hm(r["run_after"]) == (6, 0) for r in runs)
    grader.primary("runs daily at 06:00 UTC with catchup disabled", daily and dag["catchup"] is False,
                   f"catchup={dag['catchup']} runs={runs}")

    # 6. dags test: two days, then a rerun of the second day.
    shutil.rmtree(ws / "warehouse", ignore_errors=True)
    shutil.rmtree(ws / "reports", ignore_errors=True)
    landing = Path(tempfile.mkdtemp(prefix="eval-landing-"))
    shutil.copytree(LANDING, landing, dirs_exist_ok=True)
    env = g.airflow_env(ws, extra={
        "AIRFLOW_VAR_VENDOR_LANDING_DIR": str(landing),
        "AIRFLOW_CONN_FS_DEFAULT": json.dumps({"conn_type": "fs"}),
    })
    first_n = g.run_dags_test(py, ws, DAG_ID, NEIGHBOUR, env=env, timeout=DAGS_TEST_TIMEOUT_S)
    first = g.run_dags_test(py, ws, DAG_ID, DAY, env=env, timeout=DAGS_TEST_TIMEOUT_S) if first_n.ok else first_n
    grader.primary("airflow dags test succeeds", first_n.ok and first.ok,
                   "" if first.ok and first_n.ok else
                   f"failed tasks: {first.failed_tasks()}\n" + first.log[-2500:])

    def table_state() -> tuple[dict[str, Counter], str]:
        res, p = g.probe_json(py, TABLE_PROBE, ws, env=env)
        if not res or "rows" not in res:
            return {}, (res or {}).get("error") or p.tail(20)
        by_day: dict[str, Counter] = defaultdict(Counter)
        for d, sid in res["rows"]:
            by_day[d][sid] += 1
        return by_day, ""

    want = {d: Counter(r["shipment_id"] for r in landing_rows(d)) for d in (DAY, NEIGHBOUR)}
    by_day, err = table_state()
    loaded_ok = first.ok and all(by_day.get(d) == want[d] for d in want)
    grader.primary("vendor_shipments holds exactly the landing file rows per ship_date", loaded_ok,
                   err or {d: f"expected {sum(want[d].values())} rows, got {sum(by_day.get(d, Counter()).values())}"
                           for d in want})
    report_ok = all(read_report(ws, d) == expected_report(d) for d in want)
    grader.primary("carrier report published for each run date", first.ok and report_ok,
                   {d: {"expected": expected_report(d), "got": read_report(ws, d)} for d in want})

    second = g.run_dags_test(py, ws, DAG_ID, DAY, env=env, timeout=DAGS_TEST_TIMEOUT_S) if first.ok else first
    by_day2, err2 = table_state()
    idem = second.ok and all(by_day2.get(d) == want[d] for d in want) and read_report(ws, DAY) == expected_report(DAY)
    grader.primary("rerun of a day does not duplicate rows and keeps other days", idem,
                   err2 or f"second run ok={second.ok}; " + str(
                       {d: sum(by_day2.get(d, Counter()).values()) for d in want}))

    # 7. The sensor really waits for that day's file: on a day whose file has not landed,
    #    nothing downstream of a sensor may start before GATE_WINDOW_S (the run is then killed).
    #    Catches sensors on the landing directory, on the wrong file name, or on a stale path.
    gate_ok, gate_detail = sensor_gates_downstream(py, ws, landing, sensor_ids, deps)
    grader.primary("load waits for the day's file (nothing runs when the file is missing)", gate_ok, gate_detail)

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


def sensor_gates_downstream(py: str, ws: Path, landing: Path, sensor_ids: set[str],
                            deps: list[list[str]]) -> tuple[bool, str]:
    if not sensor_ids:
        return False, "no sensor tasks"
    gated = {t for t in {d for _, d in deps} | {u for u, _ in deps}
             if t not in sensor_ids and sensor_ids & ancestors(deps, t)}
    copy = g.copy_workspace(ws)
    shutil.rmtree(copy / "warehouse", ignore_errors=True)
    shutil.rmtree(copy / "reports", ignore_errors=True)
    env = g.airflow_env(copy, extra={
        "AIRFLOW_VAR_VENDOR_LANDING_DIR": str(landing),
        "AIRFLOW_CONN_FS_DEFAULT": json.dumps({"conn_type": "fs"}),
    })
    res = g.run_dags_test(py, copy, DAG_ID, MISSING_DAY, env=env, timeout=GATE_WINDOW_S)
    states = {k: v for run in res.runs for k, v in run.get("tasks", {}).items()}
    started = {k: v for k, v in states.items() if k.split("[", 1)[0] in gated and v not in NOT_STARTED}
    detail = (f"no shipments_{MISSING_DAY}.csv in the landing dir; after {GATE_WINDOW_S}s "
              f"(timed_out={res.timed_out}) task states: {states}")
    return not started, detail


def _utc_hm(stamp: str) -> tuple[int, int]:
    from datetime import datetime, timezone

    t = datetime.fromisoformat(stamp).astimezone(timezone.utc)
    return t.hour, t.minute


def _deltas(stamps: list[str]) -> list[float]:
    from datetime import datetime

    ts = [datetime.fromisoformat(s) for s in stamps]
    return [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]


if __name__ == "__main__":
    main()
