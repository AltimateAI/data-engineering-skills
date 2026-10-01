"""Carrier on-time scorecard, rebuilt whenever a new shipments batch lands."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import pendulum
from airflow.sdk import Asset, dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = PROJECT_ROOT / "output" / "warehouse" / "shipments"
SCORECARD_DIR = PROJECT_ROOT / "output" / "scorecard"
SHIPMENTS = Asset(name="shipments", uri="warehouse://shipments/batches")


@dag(
    schedule=SHIPMENTS,
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "logistics-data"},
    tags=["logistics", "reporting"],
)
def carrier_scorecard():
    @task
    def build_scorecard() -> dict:
        latest: dict[str, dict] = {}
        for batch in sorted(BATCH_DIR.glob("batch_*.csv")):
            with batch.open(newline="") as fh:
                for row in csv.DictReader(fh):
                    key = (row["updated_at"], row["event_id"])
                    seen = latest.get(row["shipment_id"])
                    if seen is None or key > (seen["updated_at"], seen["event_id"]):
                        latest[row["shipment_id"]] = row

        shipments, delivered, on_time = defaultdict(int), defaultdict(int), defaultdict(int)
        for row in latest.values():
            carrier = row["carrier"]
            shipments[carrier] += 1
            if row["status"] == "delivered":
                delivered[carrier] += 1
                on_time[carrier] += row["updated_at"][:10] <= row["promised_date"]

        SCORECARD_DIR.mkdir(parents=True, exist_ok=True)
        with (SCORECARD_DIR / "carrier_scorecard.csv").open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["carrier", "shipments", "delivered", "on_time", "on_time_rate"])
            for carrier in sorted(shipments):
                d = delivered[carrier]
                rate = f"{on_time[carrier] / d:.3f}" if d else ""
                writer.writerow([carrier, shipments[carrier], d, on_time[carrier], rate])
        return {"carriers": len(shipments), "shipments": len(latest)}

    @task
    def mark_ready(stats: dict) -> None:
        (SCORECARD_DIR / "_READY").write_text(
            f"carriers={stats['carriers']} shipments={stats['shipments']}\n"
        )

    mark_ready(build_scorecard())


carrier_scorecard()
