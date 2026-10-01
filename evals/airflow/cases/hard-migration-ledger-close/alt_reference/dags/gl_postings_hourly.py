"""Hourly incremental extract of GL postings by arrival time (``posted_at``).

Each run writes every posting that arrived after the previous run's high-water
mark (kept in XCom) up to the end of its hour, to
output/postings/batch_<hour end>.csv. Every posting must land exactly once.
"""

from __future__ import annotations

import csv

import pendulum
from airflow.sdk import CronDataIntervalTimetable, dag, task

from ledger_lib import DATA_DIR, OUTPUT_DIR

FIELDS = ["posting_id", "account", "amount_cents", "currency", "booked_at", "posted_at"]


@dag(
    schedule=CronDataIntervalTimetable("@hourly", timezone="UTC"),
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "finance-data", "retries": 2},
    tags=["ledger", "ingest"],
)
def gl_postings_hourly():
    @task
    def extract(data_interval_end=None, ti=None) -> int:
        this_batch = f"batch_{data_interval_end.strftime('%Y%m%dT%H%M')}.csv"
        cursor = None
        for batch in sorted((OUTPUT_DIR / "postings").glob("batch_*.csv")):
            if batch.name < this_batch:
                with batch.open(newline="") as fh:
                    cursor = max([cursor or ""] + [r["posted_at"] for r in csv.DictReader(fh)]) or None
        upper = data_interval_end.strftime("%Y-%m-%d %H:%M:%S")
        with (DATA_DIR / "postings.csv").open(newline="") as fh:
            rows = [r for r in csv.DictReader(fh)
                    if r["posted_at"] <= upper and (cursor is None or r["posted_at"] > cursor)]
        out = OUTPUT_DIR / "postings" / f"batch_{data_interval_end.strftime('%Y%m%dT%H%M')}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        ti.xcom_push(key="cursor", value=max((r["posted_at"] for r in rows), default=cursor))
        return len(rows)

    extract()


gl_postings_hourly()
