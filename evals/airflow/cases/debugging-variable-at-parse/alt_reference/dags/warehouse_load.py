"""Load daily completed-order revenue per region into the analytics warehouse.

The warehouse directory comes from the `warehouse_path` Airflow Variable. It is
passed to the tasks as a Jinja template, so it is resolved when a task runs and
never while the file is parsed.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import duckdb
from airflow.sdk import CronDataIntervalTimetable, dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORDERS_CSV = PROJECT_ROOT / "data" / "orders.csv"
WAREHOUSE_PATH = "{{ var.value.warehouse_path }}"


@dag(
    dag_id="warehouse_load",
    # Airflow 2 semantics: the 06:00 run covers the previous day's interval.
    schedule=CronDataIntervalTimetable("0 6 * * *", timezone="UTC"),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["warehouse"],
)
def warehouse_load():
    @task
    def extract_orders(ds=None) -> list[dict]:
        with ORDERS_CSV.open(newline="") as fh:
            return [
                row
                for row in csv.DictReader(fh)
                if row["order_date"] == ds and row["status"] == "completed"
            ]

    @task
    def aggregate_revenue(orders: list[dict]) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for order in orders:
            totals[order["region"]] += float(order["amount"])
        return {region: round(total, 2) for region, total in sorted(totals.items())}

    @task
    def load_warehouse(revenue: dict[str, float], warehouse_path: str, ds=None) -> int:
        db = Path(warehouse_path) / "warehouse.duckdb"
        db.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(db)) as con:
            con.execute(
                "create table if not exists daily_revenue "
                "(revenue_date date, region varchar, revenue decimal(12, 2))"
            )
            con.execute("delete from daily_revenue where revenue_date = ?", [ds])
            con.executemany(
                "insert into daily_revenue values (?, ?, ?)",
                [(ds, region, amount) for region, amount in revenue.items()],
            )
        return len(revenue)

    @task
    def validate_load(expected_rows: int, warehouse_path: str, ds=None) -> None:
        db = Path(warehouse_path) / "warehouse.duckdb"
        with duckdb.connect(str(db), read_only=True) as con:
            (loaded,) = con.execute(
                "select count(*) from daily_revenue where revenue_date = ?", [ds]
            ).fetchone()
        if loaded != expected_rows:
            raise ValueError(f"expected {expected_rows} rows for {ds}, found {loaded}")

    loaded = load_warehouse(aggregate_revenue(extract_orders()), warehouse_path=WAREHOUSE_PATH)
    validate_load(loaded, warehouse_path=WAREHOUSE_PATH)


warehouse_load()
