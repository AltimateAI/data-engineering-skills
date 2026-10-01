"""Daily count of orders per status, written as one CSV per day."""

from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dag(
    schedule="0 5 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["reporting"],
)
def order_status_report():
    @task
    def count_statuses(ds=None) -> str:
        with (PROJECT_ROOT / "data" / "orders.csv").open(newline="") as fh:
            counts = Counter(r["status"] for r in csv.DictReader(fh) if r["order_date"] == ds)
        out = PROJECT_ROOT / "output" / "order_status_report" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["status", "orders"])
            writer.writerows(sorted(counts.items()))
        return str(out)

    count_statuses()


order_status_report()
