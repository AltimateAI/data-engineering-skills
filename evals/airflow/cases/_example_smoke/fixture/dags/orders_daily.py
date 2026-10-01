"""Daily order totals, written as one CSV per logical date."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dag(
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["orders"],
)
def orders_daily():
    @task
    def summarize(ds=None):
        out = PROJECT_ROOT / "output" / "orders_daily" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            csv.writer(fh).writerow(["order_date", "orders"])
        return str(out)

    summarize()


orders_daily()
