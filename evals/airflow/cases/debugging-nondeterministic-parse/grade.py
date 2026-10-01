"""Grader for debugging-nondeterministic-parse.

The fixture DAG builds its task list from a slow HTTP catalog call at module
level, iterates a `set` (order depends on the per-process hash seed), and puts
`datetime.now()` in `start_date` and `description`. On Airflow 3 every parse
serializes differently, so the dag-processor writes a new DAG version on every
parse, and each parse waits on the catalog service.

The grader runs its own slow catalog service (it counts requests) and parses
the dags folder in four fresh processes, each with a different
PYTHONHASHSEED and local timezone (TZ), the last one with the clock moved
ahead by a few days. A fixed DAG serializes to the same
Airflow `dag_hash` every time, parses under the time budget and never calls
the catalog while parsing. It must also keep one `load_<table>` task per
catalog table, run the loads one at a time, keep the 01:30 UTC schedule, and
load every table when run. The task list must keep following the deployed
catalog snapshot (`config/tables.json`): a table added to the snapshot gets its
own load task without editing the DAG file.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

DAG_ID = "warehouse_ingest"
# Table the grader adds to the catalog snapshot to check the DAG follows it.
NEW_TABLE = "returns"
# Below the stand-in catalog delay, with headroom for a loaded grading machine.
PARSE_BUDGET_S = 3.0
CATALOG_DELAY_S = 4.0
# (PYTHONHASHSEED, TZ, clock shift in seconds) per parse. The seeds give three
# different `set` orders for the catalog tables; the zones are 26 hours apart,
# so any local-time `now()`/`today()` differs even at day resolution. The last
# parse runs with the clock moved 3 days 7 hours ahead, so a UTC day-anchored
# value (`pendulum.today("UTC")`, the `days_ago` replacement) differs too.
CLOCK_SHIFT_S = str(3 * 86400 + 7 * 3600)
PARSE_SCENARIOS = [("1", "UTC", "0"), ("2", "Pacific/Kiritimati", "0"), ("3", "Etc/GMT+12", "0"),
                   ("4", "UTC", CLOCK_SHIFT_S)]


def catalog_tables() -> list[str]:
    """Tables in the pristine catalog snapshot, de-duplicated."""
    return list(dict.fromkeys(json.loads((CASE_DIR / "fixture" / "config" / "tables.json").read_text())))


def expected_row_counts() -> dict[str, int]:
    out = {}
    for table in catalog_tables():
        with (CASE_DIR / "fixture" / "data" / "raw" / f"{table}.csv").open(newline="") as fh:
            out[table] = sum(1 for _ in csv.DictReader(fh))
    return out


class CatalogService:
    """Slow local stand-in for the platform team's catalog service."""

    def __init__(self) -> None:
        tables = catalog_tables()
        self.requests = 0
        self.lock = threading.Lock()
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                with service.lock:
                    service.requests += 1
                    n = service.requests
                time.sleep(CATALOG_DELAY_S)
                # Rotate the order and repeat one table, like the real service.
                names = tables[n % len(tables):] + tables[: n % len(tables)] + [tables[0]]
                body = json.dumps({"tables": [{"name": t} for t in names]}).encode()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass  # client gave up (timeout)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/api/v1/tables?domain=warehouse"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def count(self) -> int:
        with self.lock:
            return self.requests

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


PARSE_PROBE = """
import json, os
import datetime as _dtmod
import duckdb, pendulum  # noqa: F401  (bind the real datetime classes before any clock shift)
import airflow.sdk  # noqa: F401
import airflow.providers.standard.operators.empty, airflow.providers.standard.operators.python  # noqa: F401
from airflow.dag_processing.dagbag import DagBag  # noqa: F401
from airflow.models.serialized_dag import SerializedDagModel
from airflow.serialization.serialized_objects import DagSerialization

_shift = _dtmod.timedelta(seconds=float(os.environ.get("EVAL_CLOCK_SHIFT_S", "0")))
_real_dt, _real_date = _dtmod.datetime, _dtmod.date
if _shift:
    # Parse as if the dag-processor ran later: datetime/date/pendulum "now" and
    # "today" move by the shift. Constructed values stay real datetime objects.
    class _Meta(type):
        def __instancecheck__(cls, obj):
            return isinstance(obj, cls._real)

        def __subclasscheck__(cls, sub):
            return issubclass(sub, cls._real)

    class _ShiftedDatetime(_real_dt, metaclass=_Meta):
        _real = _real_dt

        def __new__(cls, *args, **kwargs):
            return _real_dt(*args, **kwargs)

        @classmethod
        def now(cls, tz=None):
            return _real_dt.now(tz) + _shift

        @classmethod
        def utcnow(cls):
            return _real_dt.utcnow() + _shift

        @classmethod
        def today(cls):
            return _real_dt.today() + _shift

    class _ShiftedDate(_real_date, metaclass=_Meta):
        _real = _real_date

        def __new__(cls, *args, **kwargs):
            return _real_date(*args, **kwargs)

        @classmethod
        def today(cls):
            return (_real_dt.now() + _shift).date()

    _dtmod.datetime, _dtmod.date = _ShiftedDatetime, _ShiftedDate
try:
    bag = dagbag()
finally:
    _dtmod.datetime, _dtmod.date = _real_dt, _real_date
dag = bag.dags.get({dag_id!r})
if dag is None:
    RESULT = {{"error": f"DAG missing; import errors: {{bag.import_errors}}"}}
else:
    data = DagSerialization.to_dict(dag)
    data = SerializedDagModel._sort_serialized_dag_dict(data)
    data["dag"].pop("fileloc", None)
    folder = os.environ["AIRFLOW__CORE__DAGS_FOLDER"]
    durations = [s.duration.total_seconds() for s in bag.dagbag_stats
                 if os.path.realpath(os.path.join(folder, s.file)) == os.path.realpath(dag.fileloc)]
    RESULT = {{"hash": SerializedDagModel.hash(DagSerialization.to_dict(dag)),
              "dag": data["dag"],
              "parse_s": max(durations) if durations else None,
              "stats": [[s.file, s.duration.total_seconds()] for s in bag.dagbag_stats]}}
"""


def differing_fields(dags: list[dict]) -> list[str]:
    keys = sorted(set().union(*(d.keys() for d in dags)))
    return [k for k in keys if len({json.dumps(d.get(k), sort_keys=True, default=str) for d in dags}) > 1]


def reachable(details: dict, src: str, dst: str) -> bool:
    seen, stack = set(), [src]
    while stack:
        for nxt in details.get(stack.pop(), {}).get("downstream", []):
            if nxt == dst:
                return True
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


def check_graph(dag: dict, loads: list[str] | None = None) -> tuple[bool, str]:
    details = dag["task_details"]
    loads = loads or [f"load_{t}" for t in catalog_tables()]
    missing = [t for t in ["start", "done", *loads] if t not in details]
    if missing:
        return False, f"missing tasks {missing}; have {dag['tasks']}"
    mapped = [t for t in loads if details[t]["mapped"]]
    problems = []
    if mapped:
        problems.append(f"mapped load tasks {mapped}")
    problems += [f"start does not precede {t}" for t in loads if not reachable(details, "start", t)]
    problems += [f"{t} does not precede done" for t in loads if not reachable(details, t, "done")]
    parallel = [f"{a}|{b}" for i, a in enumerate(loads) for b in loads[i + 1:]
                if not (reachable(details, a, b) or reachable(details, b, a))]
    if parallel:
        problems.append(f"loads that can run at the same time: {parallel[:6]}")
    return not problems, "ok" if not problems else "; ".join(problems) + f" deps={dag['deps']}"


def follows_snapshot(py: str, ws: Path, extra: dict) -> tuple[bool, str]:
    """Add a table (and a duplicate entry) to a copy of the workspace's snapshot and re-parse."""
    copy = g.copy_workspace(ws)
    try:
        snapshot = copy / "config" / "tables.json"
        if not snapshot.is_file():
            return False, "config/tables.json is missing"
        tables = json.loads(snapshot.read_text()) + [NEW_TABLE, "orders"]
        snapshot.write_text(json.dumps(tables, indent=2))
        imp = g.import_dags(py, copy, env=g.airflow_env(copy, extra=extra), timeout=300)
        dag = imp["dags"].get(DAG_ID)
        if dag is None:
            return False, f"DAG missing after adding {NEW_TABLE}: {imp['probe_error'] or imp['import_errors']}"
        ok, detail = check_graph(dag, [f"load_{t}" for t in dict.fromkeys(tables)])
        return ok, f"snapshot + {NEW_TABLE} and a duplicate entry: {detail}"
    finally:
        shutil.rmtree(copy.parent, ignore_errors=True)


def read_counts(py: str, ws: Path, db: Path):
    if not db.exists():
        return f"missing {db.relative_to(ws)}"
    res, proc = g.probe_json(py, f"""
        import duckdb
        con = duckdb.connect({str(db)!r}, read_only=True)
        names = [r[0] for r in con.execute("select table_name from information_schema.tables").fetchall()]
        RESULT = {{n[4:]: con.execute(f'select count(*) from "{{n}}"').fetchone()[0]
                  for n in names if n.startswith("raw_")}}
    """, ws)
    return res if res is not None else f"probe failed: {proc.tail(5)}"


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)
    catalog = CatalogService()
    extra = {"CATALOG_URL": catalog.url}
    try:
        imp = g.import_dags(py, ws, env=g.airflow_env(ws, extra=extra), timeout=300)
        grader.primary("DAG files import cleanly", imp["ok"] and not imp["import_errors"],
                       imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                       for k, v in imp["import_errors"].items()))
        dag = imp["dags"].get(DAG_ID)
        grader.primary(f"DAG {DAG_ID} is present", dag is not None, f"found: {sorted(imp['dags'])}")
        if dag is not None:
            ok, detail = check_graph(dag)
            grader.primary("one load_<table> task per catalog table, loads run one at a time", ok, detail)

            # Fresh parses: different hash seed, local timezone and clock each time.
            parses = []
            for seed, tz, shift in PARSE_SCENARIOS:
                env = g.airflow_env(ws, extra={**extra, "PYTHONHASHSEED": seed, "TZ": tz,
                                               "EVAL_CLOCK_SHIFT_S": shift})
                res, proc = g.probe_json(py, PARSE_PROBE.format(dag_id=DAG_ID), ws, env=env, timeout=300)
                parses.append(res if isinstance(res, dict) else {"error": proc.tail(15)})
            errors = [p["error"] for p in parses if "error" in p]
            hashes = [p.get("hash") for p in parses]
            same = not errors and len(set(hashes)) == 1
            detail = (f"probe errors: {errors}" if errors else
                      f"dag_hash per parse={hashes}; fields that differ: "
                      f"{differing_fields([p['dag'] for p in parses])}")
            grader.primary("every parse serializes to the same DAG (no new version per parse)", same, detail)

            times = [p.get("parse_s") for p in parses]
            fast = not errors and all(t is not None and t <= PARSE_BUDGET_S for t in times)
            grader.primary(f"DAG file parses in <= {PARSE_BUDGET_S}s", fast,
                           f"parse seconds={times}" + (f" errors={errors}" if errors else ""))

            calls = catalog.count()
            grader.primary("parsing never calls the catalog service", calls == 0,
                           f"{calls} catalog requests during {1 + len(PARSE_SCENARIOS)} parses")

            sched, proc = g.probe_json(py, f"""
                dag = get_dag({DAG_ID!r})
                RESULT = {{"runs": scheduled_intervals(dag, "2030-01-01T00:00:00+00:00", n=3),
                          "start_date": dag.start_date.isoformat() if dag.start_date else None,
                          "catchup": dag.catchup}}
            """, ws, env=g.airflow_env(ws, extra=extra))
            now = datetime.now(timezone.utc).isoformat()
            # Trigger timetable (runs at 01:30 from 01-01) or data-interval
            # timetable (first run at the end of the 01-01 interval) are both fine.
            ok = (sched is not None
                  and [r["run_after"] for r in sched["runs"]] in (
                      [f"2030-01-0{d}T01:30:00+00:00" for d in (1, 2, 3)],
                      [f"2030-01-0{d}T01:30:00+00:00" for d in (2, 3, 4)])
                  and sched["catchup"] is False
                  and sched["start_date"] is not None and sched["start_date"] <= now)
            grader.primary("still daily at 01:30 UTC, catchup off, start_date fixed in the past", ok,
                           f"{sched}" if sched is not None else proc.tail(10))

            ok, detail = follows_snapshot(py, ws, extra)
            grader.primary("load tasks follow the deployed catalog snapshot (config/tables.json)", ok, detail)

            # Run it (no logical date: works for any fixed start_date in the past).
            shutil.rmtree(ws / "warehouse", ignore_errors=True)
            run = g.run_dags_test(py, ws, DAG_ID, env=g.airflow_env(ws, extra=extra), timeout=600)
            grader.primary("airflow dags test succeeds", run.ok,
                           "" if run.ok else f"failed tasks={run.failed_tasks()}\n{run.log[-3000:]}")
            got = read_counts(py, ws, ws / "warehouse" / "warehouse.duckdb")
            want = expected_row_counts()
            grader.primary("every catalog table loaded into the warehouse", got == want,
                           f"expected {want}, got {got}")
    finally:
        catalog.close()

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
