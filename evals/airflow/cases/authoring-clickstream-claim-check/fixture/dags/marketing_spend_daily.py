"""Daily marketing spend per channel for the BI tool."""

from __future__ import annotations

import csv
from pathlib import Path

import pendulum
from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dag(
    schedule="30 4 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    tags=["marketing"],
)
def marketing_spend_daily():
    @task
    def spend_by_channel(ds=None) -> dict[str, float]:
        totals: dict[str, float] = {}
        with (PROJECT_ROOT / "data" / "marketing_spend.csv").open(newline="") as fh:
            for row in csv.DictReader(fh):
                if row["spend_date"] == ds:
                    totals[row["channel"]] = totals.get(row["channel"], 0.0) + float(row["spend"])
        return totals

    @task
    def publish(totals: dict[str, float], ds=None) -> None:
        out = PROJECT_ROOT / "output" / "marketing_spend" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["channel", "spend"])
            for channel in sorted(totals):
                writer.writerow([channel, round(totals[channel], 2)])

    publish(spend_by_channel())


marketing_spend_daily()
