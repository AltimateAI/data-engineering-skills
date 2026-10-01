"""End-of-day stock on hand per warehouse/SKU, plus a low-stock list (Airflow 2.11)."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    tmp.replace(path)


def compute_snapshot(ds: str) -> str:
    on_hand: dict[tuple[str, str], int] = defaultdict(int)
    with (DATA_DIR / "inventory_movements.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["movement_date"] <= ds:
                on_hand[(row["warehouse_id"], row["sku"])] += int(row["qty_change"])
    out = OUTPUT_DIR / "inventory_snapshot" / f"{ds}.csv"
    _write_csv(out, ["warehouse_id", "sku", "on_hand"], [[w, s, q] for (w, s), q in sorted(on_hand.items())])
    return str(out)


def compute_low_stock(ds: str, ti) -> str:
    snapshot = Path(ti.xcom_pull(task_ids="build_snapshot"))
    with (DATA_DIR / "reorder_points.csv").open(newline="") as fh:
        reorder = {r["sku"]: int(r["reorder_point"]) for r in csv.DictReader(fh)}
    low = []
    with snapshot.open(newline="") as fh:
        for r in csv.DictReader(fh):
            point = reorder.get(r["sku"])
            if point is not None and int(r["on_hand"]) < point:
                low.append([r["warehouse_id"], r["sku"], int(r["on_hand"]), point])
    out = OUTPUT_DIR / "low_stock" / f"{ds}.csv"
    _write_csv(out, ["warehouse_id", "sku", "on_hand", "reorder_point"], sorted(low))
    return str(out)


with DAG(
    dag_id="inventory_snapshot",
    schedule="30 2 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    default_args={"owner": "supply-chain-analytics", "retries": 1, "retry_delay": timedelta(minutes=10)},
    tags=["inventory"],
) as dag:
    build_snapshot = PythonOperator(task_id="build_snapshot", python_callable=compute_snapshot)
    flag_low_stock = PythonOperator(task_id="flag_low_stock", python_callable=compute_low_stock)
    build_snapshot >> flag_low_stock
