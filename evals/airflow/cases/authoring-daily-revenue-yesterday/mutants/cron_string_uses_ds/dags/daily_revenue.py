"""Daily revenue per store for the previous UTC calendar day.

The schedule is an explicit CronDataIntervalTimetable: the run that starts at
03:00 UTC on day D covers the interval [D-1 03:00, D 03:00), so
`data_interval_start` falls on D-1, the day being reported.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import pendulum
from airflow.sdk import CronDataIntervalTimetable, dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dag(
    schedule="0 3 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    tags=["finance"],
)
def daily_revenue():
    @task
    def aggregate(ds=None) -> str:
        day = ds
        orders: dict[str, int] = defaultdict(int)
        revenue: dict[str, float] = defaultdict(float)
        with (PROJECT_ROOT / "data" / "orders.csv").open(newline="") as fh:
            for row in csv.DictReader(fh):
                if row["order_ts"][:10] == day:
                    orders[row["store_id"]] += 1
                    revenue[row["store_id"]] += float(row["amount"])
        out = PROJECT_ROOT / "output" / "daily_revenue" / f"{day}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["store_id", "orders", "revenue"])
            for store in sorted(orders):
                writer.writerow([store, orders[store], f"{revenue[store]:.2f}"])
        return str(out)

    aggregate()


daily_revenue()
