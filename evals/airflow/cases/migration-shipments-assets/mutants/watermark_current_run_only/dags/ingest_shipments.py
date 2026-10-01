"""Hourly incremental load of carrier shipment events into the warehouse.

Each run appends one batch file with every event that arrived since the
previous run's high-water mark (the largest ``updated_at`` it loaded, kept in
XCom) up to the end of the run's interval. Publishing the batch updates the
``shipments`` asset, which triggers ``carrier_scorecard``.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pendulum
from airflow.sdk import Asset, dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "data" / "carrier_events.csv"
BATCH_DIR = PROJECT_ROOT / "output" / "warehouse" / "shipments"
SHIPMENTS = Asset("warehouse://shipments/batches")
FIELDS = ["event_id", "shipment_id", "carrier", "status", "promised_date", "updated_at"]


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
    def load_batch(data_interval_end=None, ti=None) -> int:
        # Airflow 3 blocks metadata-DB access: read the previous watermark via XCom.
        watermark = ti.xcom_pull(task_ids="load_batch", key="watermark")
        upper = data_interval_end.strftime("%Y-%m-%d %H:%M:%S")
        with SOURCE.open(newline="") as fh:
            rows = [
                r
                for r in csv.DictReader(fh)
                if r["updated_at"] <= upper and (watermark is None or r["updated_at"] > watermark)
            ]
        out = BATCH_DIR / f"batch_{data_interval_end.strftime('%Y%m%dT%H%M')}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        ti.xcom_push(key="watermark", value=max((r["updated_at"] for r in rows), default=watermark))
        return len(rows)

    load_batch()


ingest_shipments()
