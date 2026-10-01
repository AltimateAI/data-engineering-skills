"""Loads yesterday's shop orders into the local DuckDB warehouse.

The shop backend exports every order to data/orders.csv. This DAG copies the
previous day's non-cancelled orders into `orders` and then refreshes the
`daily_revenue` rollup that the finance dashboard reads.
"""

from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pendulum
from airflow.decorators import dag, task

PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_CSV = PROJECT_DIR / "data" / "orders.csv"
WAREHOUSE = PROJECT_DIR / "warehouse" / "analytics.duckdb"


@dag(
    dag_id="orders_daily_load",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "data-eng"},
    tags=["shop", "warehouse"],
)
def orders_daily_load():
    @task
    def load_orders() -> str:
        day = (datetime.now() - timedelta(days=1)).date()
        WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(WAREHOUSE))
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id    VARCHAR,
                order_date  DATE,
                customer_id VARCHAR,
                amount_usd  DECIMAL(12, 2),
                loaded_at   TIMESTAMP
            )
            """
        )
        con.execute(
            f"""
            INSERT INTO orders
            SELECT order_id,
                   CAST(order_ts AS DATE),
                   customer_id,
                   CAST(amount_usd AS DECIMAL(12, 2)),
                   now()
            FROM read_csv_auto('{SOURCE_CSV}')
            WHERE CAST(order_ts AS DATE) = ?
              AND status <> 'cancelled'
            """,
            [day],
        )
        con.close()
        return day.isoformat()

    @task
    def build_daily_revenue(day: str) -> None:
        con = duckdb.connect(str(WAREHOUSE))
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_revenue (
                order_date  DATE,
                order_count INTEGER,
                revenue_usd DECIMAL(14, 2)
            )
            """
        )
        con.execute(
            """
            INSERT INTO daily_revenue
            SELECT order_date, count(*), sum(amount_usd)
            FROM orders
            WHERE order_date = CAST(? AS DATE)
            GROUP BY order_date
            """,
            [day],
        )
        con.close()

    build_daily_revenue(load_orders())


orders_daily_load()
