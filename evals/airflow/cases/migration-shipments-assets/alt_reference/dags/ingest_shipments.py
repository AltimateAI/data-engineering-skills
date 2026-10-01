"""Hourly incremental load of carrier shipment events into the warehouse.

Each run appends one batch file with every event received after the end of
the previous successful run's interval, up to the end of this run's interval.
Publishing the batch updates the ``shipments`` asset, which triggers
``carrier_scorecard``.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pendulum
from airflow.sdk import Asset, dag, get_current_context, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "data" / "carrier_events.csv"
BATCH_DIR = PROJECT_ROOT / "output" / "warehouse" / "shipments"
SHIPMENTS = Asset(name="shipments", uri="warehouse://shipments/batches")
FIELDS = ["event_id", "shipment_id", "carrier", "status", "promised_date", "updated_at"]
TS_FORMAT = "%Y-%m-%d %H:%M:%S"


@dag(
    schedule="@hourly",
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "logistics-data", "retries": 2},
    tags=["logistics", "ingest"],
)
def ingest_shipments():
    @task(outlets=[SHIPMENTS])
    def load_batch() -> int:
        ctx = get_current_context()
        end = ctx["data_interval_end"]
        # The previous successful run loaded everything up to its interval end.
        # Airflow 3 exposes it in the context, no metadata-DB query needed.
        since = ctx.get("prev_data_interval_end_success")
        upper = end.strftime(TS_FORMAT)
        lower = since.strftime(TS_FORMAT) if since else None
        with SOURCE.open(newline="") as fh:
            rows = [
                r
                for r in csv.DictReader(fh)
                if r["updated_at"] <= upper and (lower is None or r["updated_at"] > lower)
            ]
        out = BATCH_DIR / f"batch_{end.strftime('%Y%m%dT%H%M')}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    load_batch()


ingest_shipments()
