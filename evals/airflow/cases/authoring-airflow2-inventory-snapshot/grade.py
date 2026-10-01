"""Grader for authoring-airflow2-inventory-snapshot (Airflow 2.11).

Primary checks: the new DAG imports and runs in the pinned 2.11 env (Airflow 3
idioms such as `airflow.sdk` or the standard provider do not exist there),
it is scheduled daily at 02:30 UTC with catchup off (2.11 defaults catchup to
True), and `airflow dags test` writes correct snapshot and low-stock files per
logical date, idempotently.
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

DAG_ID = "inventory_snapshot"
DAY, NEIGHBOUR = "2026-09-28", "2026-09-14"
FIXTURE_DATA = CASE_DIR / "fixture" / "data"
# Sample movements plus boundary rows (stock exactly at the reorder point, a movement on the
# run date, one after it) that the agent never sees.
GRADER_MOVEMENTS = CASE_DIR / "grader_data" / "inventory_movements.csv"


def expected(day: str) -> tuple[list[tuple], list[tuple]]:
    """(snapshot rows, low-stock rows) from the grader-owned movements; zero-stock rows dropped."""
    stock: dict[tuple[str, str], int] = defaultdict(int)
    with GRADER_MOVEMENTS.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if r["movement_date"] <= day:
                stock[(r["warehouse_id"], r["sku"])] += int(r["qty_change"])
    with (FIXTURE_DATA / "reorder_points.csv").open(newline="") as fh:
        points = {r["sku"]: int(r["reorder_point"]) for r in csv.DictReader(fh)}
    snap = sorted((w, s, q) for (w, s), q in stock.items() if q != 0)
    low = sorted((w, s, q, points[s]) for (w, s), q in stock.items() if q < points[s])
    return snap, low


def read(path: Path, cols: list[str], drop_zero: bool) -> list[tuple] | str:
    if not path.exists():
        return f"missing {path.name}"
    try:
        with path.open(newline="") as fh:
            rows = []
            for r in csv.DictReader(fh):
                vals = [r[c].strip() for c in cols]
                rows.append(tuple(v if i < 2 else int(float(v)) for i, v in enumerate(vals)))
    except (KeyError, ValueError) as exc:
        return f"unreadable {path.name}: {exc!r}"
    return sorted(r for r in rows if not (drop_zero and r[2] == 0))


def check_outputs(ws: Path, day: str) -> tuple[bool, str]:
    snap_want, low_want = expected(day)
    snap = read(ws / "output" / "inventory_snapshot" / f"{day}.csv", ["warehouse_id", "sku", "on_hand"], True)
    low = read(ws / "output" / "low_stock" / f"{day}.csv", ["warehouse_id", "sku", "on_hand", "reorder_point"], False)
    ok = snap == snap_want and low == low_want
    if ok:
        return True, ""
    snap_shown = snap if isinstance(snap, str) else snap[:5]
    return False, (f"{day}: snapshot expected {snap_want[:5]}... got {snap_shown}; "
                   f"low_stock expected {low_want} got {low}")


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    imp = g.import_dags(py, ws)
    dag = imp["dags"].get(DAG_ID)
    grader.primary("DAGs import cleanly in Airflow 2.11", imp["ok"] and not imp["import_errors"],
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
    at_0230 = len(stamps) == 3 and all(
        s.utcoffset().total_seconds() == 0 and (s.hour, s.minute) == (2, 30) for s in stamps) and all(
        (b - a).total_seconds() == 86400 for a, b in zip(stamps, stamps[1:]))
    grader.primary("scheduled daily at 02:30 UTC", at_0230, str(res) if res is not None else proc.tail(20))
    grader.primary("catchup disabled (2.11 defaults to catchup=True)", dag["catchup"] is False,
                   f"catchup={dag['catchup']}")

    shutil.rmtree(ws / "output", ignore_errors=True)
    shutil.rmtree(ws / "data", ignore_errors=True)
    shutil.copytree(FIXTURE_DATA, ws / "data")
    shutil.copyfile(GRADER_MOVEMENTS, ws / "data" / "inventory_movements.csv")
    env = g.airflow_env(ws)
    first_n = g.run_dags_test(py, ws, DAG_ID, NEIGHBOUR, env=env)
    first = g.run_dags_test(py, ws, DAG_ID, DAY, env=env) if first_n.ok else first_n
    grader.primary("airflow dags test succeeds", first_n.ok and first.ok,
                   "" if first_n.ok and first.ok else f"failed tasks: {first.failed_tasks()}\n{first.log[-2500:]}")
    ok_d, det_d = check_outputs(ws, DAY)
    ok_n, det_n = check_outputs(ws, NEIGHBOUR)
    grader.primary("snapshot and low-stock files are correct for each logical date",
                   first.ok and ok_d and ok_n, det_d + det_n)

    second = g.run_dags_test(py, ws, DAG_ID, DAY, env=env) if first.ok else first
    ok_d2, det_d2 = check_outputs(ws, DAY)
    ok_n2, det_n2 = check_outputs(ws, NEIGHBOUR)
    grader.primary("rerun is idempotent and keeps other dates", second.ok and ok_d2 and ok_n2,
                   f"second run ok={second.ok}; {det_d2}{det_n2}")

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
