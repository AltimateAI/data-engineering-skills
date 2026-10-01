"""Grader for debugging-variable-at-parse.

The fixture DAG reads an Airflow Variable at module level (fails to parse
outside the dag-processor with VARIABLE_NOT_FOUND, even when the Variable exists
in the metadata DB) and, behind that, still passes the removed
`schedule_interval` argument. A correct fix imports with no Variables at all,
keeps the task graph and the 06:00 daily schedule, and still takes the
warehouse location from the `warehouse_path` Variable at run time.
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

DAG_ID = "warehouse_load"
DAY = "2026-03-02"
TASK_CHAIN = ["extract_orders", "aggregate_revenue", "load_warehouse", "validate_load"]


def expected_revenue(day: str) -> dict[str, float]:
    """Ground truth from the pristine fixture data."""
    totals: dict[str, float] = defaultdict(float)
    with (CASE_DIR / "fixture" / "data" / "orders.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["order_date"] == day and row["status"] == "completed":
                totals[row["region"]] += float(row["amount"])
    return {k: round(v, 2) for k, v in sorted(totals.items())}


def reachable(dag: dict, src: str, dst: str) -> bool:
    details = dag["task_details"]
    seen, stack = set(), [src]
    while stack:
        cur = stack.pop()
        for nxt in details.get(cur, {}).get("downstream", []):
            if nxt == dst:
                return True
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


def read_warehouse(py: str, ws: Path, db: Path, day: str):
    """Rows of daily_revenue for ``day`` as {region: revenue}, or None if absent."""
    if not db.exists():
        return None
    res, proc = g.probe_json(py, f"""
        import duckdb
        con = duckdb.connect({str(db)!r}, read_only=True)
        rows = con.execute("select region, cast(revenue as double) from daily_revenue "
                           "where cast(revenue_date as varchar) = ?", [{day!r}]).fetchall()
        RESULT = {{r: round(v, 2) for r, v in sorted(rows)}}
    """, ws)
    return res if res is not None else f"probe failed: {proc.tail(5)}"


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    # 1. Parse with no Variables anywhere (like CI / a fresh dev box).
    imp = g.import_dags(py, ws)
    errors = "; ".join(f"{k}: {v.strip().splitlines()[-1]}" for k, v in imp["import_errors"].items())
    grader.primary("DAG files import with no Variables available",
                   imp["ok"] and not imp["import_errors"], imp["probe_error"] or errors)
    dag = imp["dags"].get(DAG_ID)
    grader.primary(f"DAG {DAG_ID} is present", dag is not None, f"found: {sorted(imp['dags'])}")

    if dag is not None:
        missing = [t for t in TASK_CHAIN if t not in dag["tasks"]]
        broken = [f"{a}->{b}" for a, b in zip(TASK_CHAIN, TASK_CHAIN[1:])
                  if a in dag["tasks"] and b in dag["tasks"] and not reachable(dag, a, b)]
        grader.primary("task graph preserved (extract -> aggregate -> load -> validate)",
                       not missing and not broken, f"missing={missing} broken={broken} deps={dag['deps']}")

        sched, proc = g.probe_json(py, f"""
            dag = get_dag({DAG_ID!r})
            RESULT = scheduled_intervals(dag, "2026-03-01T00:00:00+00:00", n=3, catchup=True)
        """, ws)
        run_after = [r["run_after"] for r in (sched or [])]
        # Either a trigger timetable (first run 03-01 06:00) or a data-interval
        # timetable (first run at the end of the 03-01 interval) is fine.
        days = [ra[:10] for ra in run_after]
        ok = (all(ra.endswith("T06:00:00+00:00") for ra in run_after)
              and days in (["2026-03-01", "2026-03-02", "2026-03-03"],
                           ["2026-03-02", "2026-03-03", "2026-03-04"])
              and dag["catchup"] is False)
        grader.primary("still scheduled daily at 06:00 UTC, catchup off", ok,
                       f"run_after={run_after} timetable={dag['timetable']} catchup={dag['catchup']} "
                       + ("" if sched is not None else proc.tail(10)))

        # 2. Run with the Variable stored in the metadata DB, pointing at a fresh dir.
        shutil.rmtree(ws / "output", ignore_errors=True)
        warehouse_dir = Path(tempfile.mkdtemp(prefix="eval-warehouse-"))
        env = g.airflow_env(ws)
        db_ready = g.ensure_db(py, env)
        setvar = g.run_cmd([str(Path(py).parent / "airflow"), "variables", "set", "warehouse_path",
                            str(warehouse_dir)], env=env, cwd=ws)
        if not (db_ready.ok and setvar.ok):
            grader.primary("airflow dags test succeeds with warehouse_path set", False,
                           db_ready.tail(10) + setvar.tail(10))
        else:
            run = g.run_dags_test(py, ws, DAG_ID, DAY, env=env)
            grader.primary("airflow dags test succeeds with warehouse_path set", run.ok,
                           "" if run.ok else f"failed tasks={run.failed_tasks()}\n{run.log[-3000:]}")
            got = read_warehouse(py, ws, warehouse_dir / "warehouse.duckdb", DAY)
            want = expected_revenue(DAY)
            grader.primary("revenue loaded into the warehouse the Variable points to", got == want,
                           f"expected {want}, got {got} (warehouse_path={warehouse_dir})")
        shutil.rmtree(warehouse_dir, ignore_errors=True)

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
