"""Grader for scheduling-idempotent-orders-load (Airflow 2.11).

The DAG must load exactly the day its run covers, and re-running a day must
converge to the correct rows without touching the neighbouring day.

Runs are executed as the SCHEDULER would create them: the grader takes the
first scheduled run that starts on/after a given instant from the DAG's own
timetable and executes it with ``dag.test`` using that run's logical date and
data interval. (``airflow dags test`` alone gives manual-run intervals, which
differ from scheduled ones on 2.x.) A plain ``airflow dags test`` is checked
separately.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

DAG_ID = "orders_daily_load"
PREV_DAY, DAY = "2026-03-09", "2026-03-10"
WAREHOUSE_REL = Path("warehouse") / "analytics.duckdb"

# ---------------------------------------------------------------------------
# Scheduled-run simulation (shared pattern across scheduling-* cases)
# ---------------------------------------------------------------------------
_SIM_CODE = r'''
import pendulum
from airflow.timetables.base import DataInterval, TimeRestriction
dag = get_dag(DAG_ID)
tt = core_timetable(dag)
not_before = pendulum.parse(NOT_BEFORE)
earliest = not_before.subtract(days=10)
last, info = None, None
for _ in range(2000):
    nxt = tt.next_dagrun_info(last_automated_data_interval=last,
                              restriction=TimeRestriction(earliest=earliest, latest=None, catchup=True))
    if nxt is None:
        break
    if nxt.run_after >= not_before:
        info = nxt
        break
    last = nxt.data_interval
if info is None:
    raise SystemExit("no scheduled run at or after " + NOT_BEFORE)
di = info.data_interval
logical = info.logical_date
_patched = lambda self, run_after: DataInterval(di.start, di.end)
type(tt).infer_manual_data_interval = _patched
type(dag.timetable).infer_manual_data_interval = _patched
print("SIMRUN", logical, di.start, di.end, info.run_after, flush=True)
params = dag.test.__code__.co_varnames
dr = dag.test(**({"logical_date": logical} if "logical_date" in params else {"execution_date": logical}))
RESULT = {"state": str(getattr(dr.state, "value", dr.state)) if dr is not None else None,
          "logical_date": logical.isoformat(), "start": di.start.isoformat(), "end": di.end.isoformat(),
          "run_after": info.run_after.isoformat()}
'''


def scheduled_run(py: str, ws: Path, dag_id: str, not_before: str) -> tuple[bool, dict | None, str]:
    """Execute the first scheduled run of ``dag_id`` with run_after >= ``not_before``.

    Every call uses a fresh metadata DB, so a re-run always really executes."""
    env = g.airflow_env(ws)
    db = g.ensure_db(py, env)
    if not db.ok:
        return False, None, "db migrate failed: " + db.tail(20)
    code = f"DAG_ID = {dag_id!r}\nNOT_BEFORE = {not_before!r}\n" + _SIM_CODE
    res, proc = g.probe_json(py, code, ws, env=env)
    ok = bool(res) and res.get("state") == "success"
    return ok, res, proc.tail(40)


# ---------------------------------------------------------------------------
# Ground truth and warehouse reads
# ---------------------------------------------------------------------------


def expected() -> tuple[dict, dict]:
    """(orders per date {date: {order_id: (customer, amount)}}, revenue {date: (count, sum)})."""
    orders: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
    with (CASE_DIR / "fixture" / "data" / "orders.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["status"] == "cancelled":
                continue
            orders[row["order_ts"][:10]][row["order_id"]] = (row["customer_id"], f"{Decimal(row['amount_usd']):.2f}")
    revenue = {d: (len(o), f"{sum(Decimal(a) for _, a in o.values()):.2f}") for d, o in orders.items()}
    return orders, revenue


_READ_CODE = r'''
import duckdb, json, sys
con = duckdb.connect(sys.argv[1], read_only=True)
out = {}
out["orders"] = [[str(r[0]), str(r[1]), str(r[2]), f"{float(r[3]):.2f}"] for r in con.execute(
    "SELECT order_id, CAST(order_date AS VARCHAR), customer_id, amount_usd FROM orders").fetchall()]
out["revenue"] = [[str(r[0]), int(r[1]), f"{float(r[2]):.2f}"] for r in con.execute(
    "SELECT CAST(order_date AS VARCHAR), order_count, revenue_usd FROM daily_revenue").fetchall()]
print("__WH__" + json.dumps(out))
'''


def read_warehouse(py: str, ws: Path) -> tuple[dict | None, str]:
    db = ws / WAREHOUSE_REL
    if not db.exists():
        return None, f"{WAREHOUSE_REL} does not exist"
    res = g.run_cmd([py, "-c", _READ_CODE, str(db)], env=g.scrubbed_environ(), timeout=120)
    for line in res.stdout.splitlines():
        if line.startswith("__WH__"):
            return json.loads(line[6:]), ""
    return None, res.tail(10)


def check_days(wh: dict | None, days: list[str], exp_orders: dict, exp_rev: dict) -> tuple[bool, str]:
    """Exactly the expected rows for ``days`` (no duplicates) and no rows for any other day."""
    if wh is None:
        return False, "warehouse unreadable"
    problems = []
    by_day: dict[str, list[list[str]]] = defaultdict(list)
    for r in wh["orders"]:
        by_day[r[1]].append(r)
    rev_by_day: dict[str, list] = defaultdict(list)
    for r in wh["revenue"]:
        rev_by_day[r[0]].append(r)
    extra_days = sorted((set(by_day) | set(rev_by_day)) - set(days))
    if extra_days:
        problems.append(f"rows for unexpected days {extra_days}")
    for d in days:
        rows = by_day.get(d, [])
        ids = [r[0] for r in rows]
        if len(ids) != len(set(ids)):
            problems.append(f"{d}: duplicate order_ids ({len(ids)} rows, {len(set(ids))} distinct)")
        got = {r[0]: (r[2], r[3]) for r in rows}
        if got != exp_orders.get(d, {}):
            missing = sorted(set(exp_orders.get(d, {})) - set(got))
            extra = sorted(set(got) - set(exp_orders.get(d, {})))
            wrong = sorted(k for k in set(got) & set(exp_orders.get(d, {})) if got[k] != exp_orders[d][k])
            problems.append(f"{d}: orders differ (missing {missing[:5]}, unexpected {extra[:5]}, wrong values {wrong[:5]})")
        rev = rev_by_day.get(d, [])
        want = [d, exp_rev[d][0], exp_rev[d][1]]
        if rev != [want]:
            problems.append(f"{d}: daily_revenue {rev} != [{want}]")
    return not problems, "; ".join(problems)


_CORRUPT_CODE = r'''
import duckdb, sys
day = sys.argv[2]
con = duckdb.connect(sys.argv[1])
ids = [r[0] for r in con.execute(
    "SELECT order_id FROM orders WHERE CAST(order_date AS VARCHAR) = ? ORDER BY order_id", [day]).fetchall()]
# A crashed attempt left the day half-written: two orders missing, stale amounts, stale rollup.
for oid in ids[:2]:
    con.execute("DELETE FROM orders WHERE order_id = ?", [oid])
con.execute("UPDATE orders SET amount_usd = amount_usd + 1000 WHERE CAST(order_date AS VARCHAR) = ?", [day])
con.execute("UPDATE daily_revenue SET order_count = 1, revenue_usd = 1 WHERE CAST(order_date AS VARCHAR) = ?", [day])
con.close()
print("CORRUPTED", len(ids))
'''


def main() -> None:
    args = g.parse_args()
    ws, py = Path(args.workspace), sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)
    exp_orders, exp_rev = expected()

    imp = g.import_dags(py, ws)
    dag = imp["dags"].get(DAG_ID)
    grader.primary("DAGs import cleanly", imp["ok"] and not imp["import_errors"],
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items()))
    grader.primary(f"DAG {DAG_ID} exists", dag is not None, f"found: {sorted(imp['dags'])}")

    if dag is not None:
        # 1. Plain `airflow dags test` on a scratch copy (manual-run semantics).
        scratch = g.copy_workspace(ws)
        shutil.rmtree(scratch / "warehouse", ignore_errors=True)
        manual = g.run_dags_test(py, scratch, DAG_ID, DAY, env=g.airflow_env(scratch))
        grader.primary("airflow dags test succeeds", manual.ok,
                       "" if manual.ok else f"failed tasks {manual.failed_tasks()}: {manual.log[-2500:]}")

        # 2. Scheduled runs for PREV_DAY then DAY against an empty warehouse.
        shutil.rmtree(ws / "warehouse", ignore_errors=True)
        ok_prev, res_prev, log_prev = scheduled_run(py, ws, DAG_ID, f"{DAY}T00:00:00+00:00")
        ok_day, res_day, log_day = scheduled_run(py, ws, DAG_ID, "2026-03-11T00:00:00+00:00")
        wh, why = read_warehouse(py, ws)
        passed, detail = check_days(wh, [PREV_DAY, DAY], exp_orders, exp_rev)
        runs_ok = ok_prev and ok_day
        grader.primary(
            "scheduled runs load exactly their own day",
            runs_ok and passed,
            (f"runs: {res_prev}, {res_day}; " if runs_ok else f"run failed: {log_prev if not ok_prev else log_day}; ")
            + (detail or why),
        )

        # 3. Plain re-run of DAY: nothing may be duplicated, PREV_DAY untouched.
        ok_again, res_again, log_again = scheduled_run(py, ws, DAG_ID, "2026-03-11T00:00:00+00:00")
        wh, why = read_warehouse(py, ws)
        passed, detail = check_days(wh, [PREV_DAY, DAY], exp_orders, exp_rev)
        grader.primary("re-running a day creates no duplicates and keeps the previous day",
                       runs_ok and ok_again and passed,
                       (detail or why) if ok_again else f"re-run failed: {log_again}")

        # 4. Simulated partial write of DAY, then re-run: must converge again.
        db = ws / WAREHOUSE_REL
        corrupt = g.run_cmd([py, "-c", _CORRUPT_CODE, str(db), DAY], env=g.scrubbed_environ(), timeout=120) \
            if db.exists() else None
        if corrupt is None or not corrupt.ok:
            grader.primary("re-run repairs a partially written day", False,
                           "could not simulate partial write: " + (corrupt.tail(10) if corrupt else "no warehouse"))
        else:
            ok_fix, res_fix, log_fix = scheduled_run(py, ws, DAG_ID, "2026-03-11T00:00:00+00:00")
            wh, why = read_warehouse(py, ws)
            passed, detail = check_days(wh, [PREV_DAY, DAY], exp_orders, exp_rev)
            grader.primary("re-run repairs a partially written day", runs_ok and ok_fix and passed,
                           (detail or why) if ok_fix else f"re-run failed: {log_fix}")

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
