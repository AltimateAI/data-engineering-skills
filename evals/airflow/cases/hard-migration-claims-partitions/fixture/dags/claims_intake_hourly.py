"""Hourly intake of clearing-house claims into service-date partitions.

Every claim received during the hour is appended to
output/lake/claims/service_date=<day>/received_<YYYYMMDDTHH>.csv, and every
partition touched is attached to the ``claims-by-service-date`` alias with the
number of claims it received.
"""

from __future__ import annotations

import csv
from collections import defaultdict

import pendulum
from airflow.decorators import dag, task

from claims_lib import LAKE
from claims_lib.assets import CLAIMS_BY_SERVICE_DATE, partition_dataset
from claims_lib.hooks import ClaimsExportHook

FIELDS = ["claim_id", "provider_id", "service_date", "billed_cents", "status", "received_at"]


@dag(
    schedule_interval="@hourly",
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "claims-data", "retries": 2},
    tags=["claims", "ingest"],
)
def claims_intake_hourly():
    @task(outlets=[CLAIMS_BY_SERVICE_DATE])
    def land_claims(data_interval_start=None, data_interval_end=None, outlet_events=None) -> int:
        lo = data_interval_start.strftime("%Y-%m-%d %H:%M:%S")
        hi = data_interval_end.strftime("%Y-%m-%d %H:%M:%S")
        by_day: dict[str, list[dict]] = defaultdict(list)
        for row in ClaimsExportHook().read("claims_export.csv"):
            if lo <= row["received_at"] < hi:
                by_day[row["service_date"]].append(row)
        for day, rows in sorted(by_day.items()):
            path = LAKE / "claims" / f"service_date={day}" / f"received_{data_interval_start.strftime('%Y%m%dT%H')}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            outlet_events[CLAIMS_BY_SERVICE_DATE].add(partition_dataset(day), extra={"claims": len(rows)})
        return sum(len(r) for r in by_day.values())

    land_claims()


claims_intake_hourly()
