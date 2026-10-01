"""Daily revenue per region (Airflow 3, TaskFlow).

The DAG fires at 04:15 UTC every day and reports on the previous UTC business
day. Under a cron trigger the logical date is the fire time itself, so the
business day is derived explicitly as ``logical_date - 1 day``.
"""

from __future__ import annotations

import csv
import json
from datetime import timedelta
from pathlib import Path

import duckdb
import pendulum
from airflow.sdk import CronTriggerTimetable, dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORDERS_PATH = PROJECT_ROOT / "data" / "orders.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"

QUERY = """
SELECT region, COUNT(*) AS orders, CAST(SUM(amount) AS DOUBLE) AS revenue
FROM read_csv(?, header = true, columns = {
    'order_id': 'VARCHAR', 'order_ts': 'TIMESTAMP', 'region': 'VARCHAR',
    'amount': 'DECIMAL(12, 2)', 'status': 'VARCHAR'})
WHERE status = 'completed' AND order_ts >= ? AND order_ts < ?
GROUP BY region
ORDER BY region
"""


def business_day(logical_date) -> pendulum.Date:
    return pendulum.instance(logical_date).in_timezone("UTC").date().subtract(days=1)


@dag(
    dag_id="daily_revenue",
    schedule=CronTriggerTimetable("15 4 * * *", timezone="UTC"),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "finance-data", "retries": 2, "retry_delay": timedelta(minutes=10)},
    tags=["finance", "revenue"],
)
def daily_revenue():
    @task(task_id="load_daily_revenue")
    def load(logical_date=None) -> str:
        day = business_day(logical_date)
        start = pendulum.datetime(day.year, day.month, day.day)
        rows = duckdb.execute(
            QUERY, [str(ORDERS_PATH), start.naive(), start.add(days=1).naive()]
        ).fetchall()
        out = OUTPUT_DIR / "daily_revenue" / f"{day.isoformat()}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["region", "orders", "revenue"])
            for region, orders, revenue in rows:
                writer.writerow([region, orders, f"{revenue:.2f}"])
        return day.isoformat()

    @task(task_id="publish_manifest")
    def publish(day: str, logical_date=None) -> None:
        out = OUTPUT_DIR / "manifests" / f"{day}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"business_date": day, "logical_ts": str(logical_date)}))

    publish(load())


daily_revenue()
