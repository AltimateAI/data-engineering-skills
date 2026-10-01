"""Loads one day of shop orders into the local DuckDB warehouse.

The shop backend exports every order to data/orders.csv. Each run owns the day
covered by its data interval: it replaces that day's rows in `orders` and
`daily_revenue` inside one transaction, so re-runs, retries and backfills
converge to the same result and never touch other days.
"""

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
    def load_day(data_interval_start=None, data_interval_end=None) -> None:
        start = data_interval_start.naive() if hasattr(data_interval_start, "naive") else data_interval_start
        end = data_interval_end.naive() if hasattr(data_interval_end, "naive") else data_interval_end
        WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(WAREHOUSE))
        try:
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
                """
                CREATE TABLE IF NOT EXISTS daily_revenue (
                    order_date  DATE,
                    order_count INTEGER,
                    revenue_usd DECIMAL(14, 2)
                )
                """
            )
            con.execute("BEGIN TRANSACTION")
        except Exception:
            con.close()
            raise
        try:
            con.execute(
                "DELETE FROM orders WHERE order_date >= CAST(? AS DATE) AND order_date < CAST(? AS DATE)",
                [start, end],
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
                WHERE CAST(order_ts AS TIMESTAMP) >= ?
                  AND CAST(order_ts AS TIMESTAMP) < ?
                  AND status <> 'cancelled'
                """,
                [start, end],
            )
            con.execute(
                "DELETE FROM daily_revenue WHERE order_date >= CAST(? AS DATE) AND order_date < CAST(? AS DATE)",
                [start, end],
            )
            con.execute(
                """
                INSERT INTO daily_revenue
                SELECT order_date, count(*), sum(amount_usd)
                FROM orders
                WHERE order_date >= CAST(? AS DATE) AND order_date < CAST(? AS DATE)
                GROUP BY order_date
                """,
                [start, end],
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    load_day()


orders_daily_load()
