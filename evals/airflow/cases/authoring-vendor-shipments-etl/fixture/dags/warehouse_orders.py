"""Load the daily order export into the warehouse and refresh the orders mart."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = PROJECT_ROOT / "warehouse" / "analytics.duckdb"
ORDERS_EXPORT = PROJECT_ROOT / "data" / "orders_export.csv"


@dag(
    schedule="0 4 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "logistics-analytics", "retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["orders", "warehouse"],
)
def warehouse_orders():
    @task
    def load_orders(ds=None):
        import duckdb

        WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(WAREHOUSE)) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS orders (order_id VARCHAR, amount DOUBLE, order_date DATE)"
            )
            # Replace the day's rows so a rerun never duplicates them.
            con.execute("DELETE FROM orders WHERE order_date = CAST(? AS DATE)", [ds])
            con.execute(
                "INSERT INTO orders SELECT order_id, amount, CAST(order_date AS DATE) "
                "FROM read_csv_auto(?) WHERE CAST(order_date AS DATE) = CAST(? AS DATE)",
                [str(ORDERS_EXPORT), ds],
            )
            return con.execute(
                "SELECT count(*) FROM orders WHERE order_date = CAST(? AS DATE)", [ds]
            ).fetchone()[0]

    refresh_orders_mart = BashOperator(
        task_id="refresh_orders_mart",
        bash_command=f"{PROJECT_ROOT}/scripts/refresh_orders_mart.sh {{{{ ds }}}}",
    )

    load_orders() >> refresh_orders_mart


warehouse_orders()
