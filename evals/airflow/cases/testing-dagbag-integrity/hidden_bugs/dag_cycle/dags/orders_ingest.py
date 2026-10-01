"""Load the daily orders export into the warehouse and publish a summary file."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
WAREHOUSE_PATH = PROJECT_ROOT / "warehouse.duckdb"

DEFAULT_ARGS = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    schedule="0 2 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["orders", "ingest"],
)
def orders_ingest():
    @task
    def extract_orders(ds=None) -> list[dict]:
        with (DATA_DIR / "orders.csv").open(newline="") as fh:
            return [row for row in csv.DictReader(fh) if row["order_date"] == ds]

    @task
    def validate_orders(rows: list[dict]) -> list[dict]:
        bad = [r["order_id"] for r in rows if not r["order_id"] or float(r["amount"]) < 0]
        if bad:
            raise ValueError(f"invalid orders: {bad}")
        return rows

    @task
    def load_orders(rows: list[dict], ds=None) -> int:
        import duckdb

        con = duckdb.connect(str(WAREHOUSE_PATH))
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS orders "
                "(order_id VARCHAR, order_date DATE, customer_id VARCHAR, amount DOUBLE)"
            )
            con.execute("DELETE FROM orders WHERE order_date = ?", [ds])
            con.executemany(
                "INSERT INTO orders VALUES (?, ?, ?, ?)",
                [[r["order_id"], r["order_date"], r["customer_id"], float(r["amount"])] for r in rows],
            )
        finally:
            con.close()
        return len(rows)

    @task
    def publish_summary(loaded: int, ds=None) -> str:
        out = OUTPUT_DIR / "orders_summary" / f"{ds}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"date": ds, "orders_loaded": loaded}))
        return str(out)

    extracted = extract_orders()
    summary = publish_summary(load_orders(validate_orders(extracted)))
    # re-extract once the summary is out so late orders are picked up
    summary >> extracted


orders_ingest()
