"""Vendor payment run at 18:00 New York time on business days.

Pays every payables posting booked since the previous payment run (Monday's
run also covers the weekend). Output: output/payments/<ds>.csv
"""

from __future__ import annotations

import csv

import pendulum
from airflow.decorators import dag, task

from ledger_lib import DATA_DIR, OUTPUT_DIR

NEW_YORK = pendulum.timezone("America/New_York")


@dag(
    schedule_interval="0 18 * * 1-5",
    start_date=pendulum.datetime(2026, 3, 2, tz=NEW_YORK),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "accounts-payable", "retries": 1},
    tags=["ledger", "payments"],
)
def vendor_payments_weekday():
    @task
    def payment_run(ds=None, data_interval_start=None, data_interval_end=None) -> int:
        lo = data_interval_start.in_timezone("UTC").strftime("%Y-%m-%d %H:%M:%S")
        hi = data_interval_end.in_timezone("UTC").strftime("%Y-%m-%d %H:%M:%S")
        with (DATA_DIR / "postings.csv").open(newline="") as fh:
            due = [r for r in csv.DictReader(fh)
                   if r["account"] == "2000-payables" and lo <= r["booked_at"] < hi]
        out = OUTPUT_DIR / "payments" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["posting_id", "amount_cents", "currency", "booked_at"])
            for r in sorted(due, key=lambda r: r["booked_at"]):
                writer.writerow([r["posting_id"], r["amount_cents"], r["currency"], r["booked_at"]])
        return len(due)

    payment_run()


vendor_payments_weekday()
