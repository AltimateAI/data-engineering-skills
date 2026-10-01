"""Daily billing of the previous UTC day, then publication of the invoice batch.

``bill`` prices every metered hour of the day (latest rollup wins for an hour)
with that day's tariffs and writes output/billing/<day>.csv. ``publish_invoices``
copies it into the finance dropbox (``[metering] invoice_dropbox``) as the
invoice batch file.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import pendulum
from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator

from meter_lib.assets import LAKE, PROJECT_ROOT
from meter_lib.tariffs import tariff_band

ROLLUP_DIR = PROJECT_ROOT / "output" / "rollup"
BILLING_DIR = PROJECT_ROOT / "output" / "billing"


@dag(
    schedule_interval="30 2 * * *",
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    template_searchpath=[str(Path(__file__).parent / "scripts")],
    default_args={"owner": "metering-finance", "retries": 1},
    tags=["metering", "billing"],
)
def billing_daily():
    @task
    def bill(data_interval_start=None) -> str:
        day = data_interval_start.strftime("%Y-%m-%d")
        rates = {}
        with (LAKE / "tariffs" / f"{day}.csv").open() as fh:
            for line in fh:
                _, band, cents = line.strip().split(",")
                rates[band] = int(cents)

        usage: dict[tuple[str, str], float] = {}
        for path in sorted(ROLLUP_DIR.glob("usage_*.csv")):  # later rollups win
            with path.open(newline="") as fh:
                for row in csv.DictReader(fh):
                    if row["hour"].startswith(day):
                        usage[(row["meter_id"], row["hour"])] = float(row["kwh"])

        totals: dict[tuple[str, str], float] = defaultdict(float)
        for (meter, hour), kwh in usage.items():
            totals[(meter, tariff_band(int(hour[11:13])))] += kwh

        BILLING_DIR.mkdir(parents=True, exist_ok=True)
        with (BILLING_DIR / f"{day}.csv").open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["meter_id", "band", "kwh", "amount_cents"])
            for (meter, band), kwh in sorted(totals.items()):
                writer.writerow([meter, band, f"{kwh:.1f}", round(kwh * rates[band])])
        return day

    publish = BashOperator(
        task_id="publish_invoices",
        bash_command="publish_invoices.sh",
        env={"PROJECT_ROOT": str(PROJECT_ROOT)},
        append_env=True,
    )
    bill() >> publish


billing_daily()
