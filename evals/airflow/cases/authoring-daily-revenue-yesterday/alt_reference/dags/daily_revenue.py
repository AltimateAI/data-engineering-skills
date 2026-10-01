"""Daily revenue: cron-triggered at 03:00 UTC, reports the day before the trigger."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task

ROOT = Path(__file__).resolve().parents[1]


@dag(schedule="0 3 * * *", start_date=datetime(2026, 8, 1), catchup=False, tags=["finance"])
def daily_revenue():
    @task
    def report(**context) -> str:
        import duckdb

        # Cron schedules trigger at the tick: data_interval_end is the 03:00 trigger time.
        trigger = context["data_interval_end"]
        day = (trigger - timedelta(days=1)).strftime("%Y-%m-%d")
        out = ROOT / "output" / "daily_revenue" / f"{day}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        duckdb.sql(
            f"""
            COPY (
                SELECT store_id, count(*) AS orders, round(sum(amount), 2) AS revenue
                FROM read_csv('{ROOT / "data" / "orders.csv"}', timestampformat = '%Y-%m-%d %H:%M:%S')
                WHERE CAST(order_ts AS DATE) = DATE '{day}'
                GROUP BY store_id ORDER BY store_id
            ) TO '{out}' (HEADER, DELIMITER ',')
            """
        )
        return str(out)

    report()


daily_revenue()
