"""Loads the run's day of shop orders into the local DuckDB warehouse (upsert style)."""

from pathlib import Path

import duckdb
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_CSV = PROJECT_DIR / "data" / "orders.csv"
WAREHOUSE = PROJECT_DIR / "warehouse" / "analytics.duckdb"


def _connect():
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE))
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id    VARCHAR PRIMARY KEY,
            order_date  DATE,
            customer_id VARCHAR,
            amount_usd  DECIMAL(12, 2),
            loaded_at   TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_revenue (
            order_date  DATE PRIMARY KEY,
            order_count INTEGER,
            revenue_usd DECIMAL(14, 2)
        )
        """
    )
    return con


def upsert_orders(ds: str) -> None:
    """Upsert every non-cancelled order placed on ``ds`` (keyed by order_id)."""
    con = _connect()
    try:
        con.execute(
            f"""
            INSERT OR REPLACE INTO orders
            SELECT order_id, CAST(order_ts AS DATE), customer_id,
                   CAST(amount_usd AS DECIMAL(12, 2)), now()
            FROM read_csv_auto('{SOURCE_CSV}')
            WHERE CAST(order_ts AS DATE) = CAST(? AS DATE) AND status <> 'cancelled'
            """,
            [ds],
        )
    finally:
        con.close()


def upsert_revenue(ds: str) -> None:
    con = _connect()
    try:
        con.execute(
            """
            INSERT OR REPLACE INTO daily_revenue
            SELECT order_date, count(*), sum(amount_usd)
            FROM orders WHERE order_date = CAST(? AS DATE)
            GROUP BY order_date
            """,
            [ds],
        )
    finally:
        con.close()


with DAG(
    dag_id="orders_daily_load",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "data-eng"},
    tags=["shop", "warehouse"],
):
    orders = PythonOperator(task_id="upsert_orders", python_callable=upsert_orders, op_kwargs={"ds": "{{ ds }}"})
    revenue = PythonOperator(task_id="upsert_revenue", python_callable=upsert_revenue, op_kwargs={"ds": "{{ ds }}"})
    orders >> revenue
