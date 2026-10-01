"""Daily marketing spend per channel, from the ad platforms' CSV drop."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

DEFAULT_ARGS = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    schedule="30 5 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["marketing"],
)
def marketing_spend():
    # Retrying re-pulls the whole drop and double counts, so fail fast instead.
    @task(retries=0)
    def fetch_spend(ds=None) -> list[dict]:
        with (DATA_DIR / "marketing_spend.csv").open(newline="") as fh:
            return [row for row in csv.DictReader(fh) if row["spend_date"] == ds]

    @task
    def spend_by_channel(rows: list[dict], ds=None) -> str:
        totals: dict[str, float] = defaultdict(float)
        for row in rows:
            totals[row["channel"]] += float(row["spend_usd"])
        out = OUTPUT_DIR / "marketing_spend" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["channel", "spend_usd"])
            for channel in sorted(totals):
                writer.writerow([channel, f"{totals[channel]:.2f}"])
        return str(out)

    spend_by_channel(fetch_spend())


marketing_spend()
