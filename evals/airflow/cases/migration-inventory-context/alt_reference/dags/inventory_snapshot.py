"""Nightly inventory snapshot for the fulfilment centre (Airflow 3, TaskFlow).

Writes stock on hand per SKU at the end of each daily interval with the change
against the previous day's snapshot, then an audit record for alerting.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pendulum
from airflow.sdk import DeltaDataIntervalTimetable, dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOVEMENTS = PROJECT_ROOT / "data" / "stock_movements.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOW_STOCK_THRESHOLD = 20


def read_snapshot(day: str) -> dict[str, int]:
    path = OUTPUT_DIR / "inventory" / f"{day}.csv"
    if not path.exists():
        return {}
    with path.open(newline="") as fh:
        return {row["sku"]: int(row["on_hand"]) for row in csv.DictReader(fh)}


@dag(
    schedule=DeltaDataIntervalTimetable(timedelta(days=1)),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "warehouse-ops", "retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["inventory"],
)
def inventory_snapshot():
    @task(multiple_outputs=True)
    def build_snapshot(data_interval_start=None, data_interval_end=None) -> dict:
        day = data_interval_start.strftime("%Y-%m-%d")
        prev_day = data_interval_start.subtract(days=1).strftime("%Y-%m-%d")
        on_hand: dict[str, int] = defaultdict(int)
        with MOVEMENTS.open(newline="") as fh:
            for row in csv.DictReader(fh):
                moved_at = datetime.fromisoformat(row["moved_at"]).replace(tzinfo=timezone.utc)
                if moved_at < data_interval_end:
                    on_hand[row["sku"]] += int(row["qty"])
        previous = read_snapshot(prev_day)
        out = OUTPUT_DIR / "inventory" / f"{day}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["sku", "on_hand", "change"])
            for sku in sorted(on_hand):
                writer.writerow([sku, on_hand[sku], on_hand[sku] - previous[sku] if sku in previous else ""])
        return {
            "day": day,
            "sku_count": len(on_hand),
            "low_stock": sorted(s for s, q in on_hand.items() if q < LOW_STOCK_THRESHOLD),
        }

    @task
    def audit_snapshot(summary: dict) -> None:
        out = OUTPUT_DIR / "audit" / f"{summary['day']}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        record = {k: summary[k] for k in ("day", "sku_count", "low_stock")}
        out.write_text(json.dumps(record, sort_keys=True))

    audit_snapshot(build_snapshot())


inventory_snapshot()
