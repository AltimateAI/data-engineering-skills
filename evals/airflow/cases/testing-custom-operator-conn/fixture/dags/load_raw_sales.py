"""Load the nightly sales exports into the raw layer of the warehouse."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import DAG
from warehouse.operators import CsvPartitionToDuckDBOperator

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

with DAG(
    dag_id="load_raw_sales",
    schedule="0 3 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"owner": "data-platform", "retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["warehouse", "raw"],
):
    load_orders = CsvPartitionToDuckDBOperator(
        task_id="load_orders",
        csv_path=str(DATA_DIR / "orders.csv"),
        table="orders",
        partition_column="order_date",
        partition_date="{{ ds }}",
        duckdb_conn_id="warehouse",
    )
    load_refunds = CsvPartitionToDuckDBOperator(
        task_id="load_refunds",
        csv_path=str(DATA_DIR / "refunds.csv"),
        table="refunds",
        partition_column="refund_date",
        partition_date="{{ ds }}",
        duckdb_conn_id="warehouse",
    )

    load_orders >> load_refunds
