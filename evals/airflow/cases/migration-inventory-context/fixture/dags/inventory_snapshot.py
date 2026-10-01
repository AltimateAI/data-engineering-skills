"""Nightly inventory snapshot for the fulfilment centre.

For every daily interval it writes the stock on hand per SKU at the END of the
interval (``output/inventory/<ds>.csv``), with the change against the previous
day's snapshot, and then an audit record (``output/audit/<ds>.json``) that the
replenishment team's alerting reads.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator, get_current_context

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOVEMENTS = PROJECT_ROOT / "data" / "stock_movements.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOW_STOCK_THRESHOLD = 20


def _snapshot_path(day: str) -> Path:
    return OUTPUT_DIR / "inventory" / f"{day}.csv"


def _read_snapshot(day: str) -> dict[str, int]:
    path = _snapshot_path(day)
    if not path.exists():
        return {}
    with path.open(newline="") as fh:
        return {row["sku"]: int(row["on_hand"]) for row in csv.DictReader(fh)}


def build_snapshot(ds=None, execution_date=None, prev_ds=None, ti=None, **kwargs):
    as_of = execution_date + timedelta(days=1)  # end of the day being snapshotted
    on_hand: dict[str, int] = defaultdict(int)
    with MOVEMENTS.open(newline="") as fh:
        for row in csv.DictReader(fh):
            moved_at = datetime.fromisoformat(row["moved_at"]).replace(tzinfo=timezone.utc)
            if moved_at < as_of:
                on_hand[row["sku"]] += int(row["qty"])

    previous = _read_snapshot(prev_ds)
    out = _snapshot_path(ds)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["sku", "on_hand", "change"])
        for sku in sorted(on_hand):
            change = on_hand[sku] - previous[sku] if sku in previous else ""
            writer.writerow([sku, on_hand[sku], change])

    ti.xcom_push(key="sku_count", value=len(on_hand))
    ti.xcom_push(key="low_stock", value=sorted(s for s, q in on_hand.items() if q < LOW_STOCK_THRESHOLD))


def audit_snapshot(**kwargs):
    context = get_current_context()
    day = context["execution_date"].strftime("%Y-%m-%d")
    ti = kwargs["ti"]
    record = {
        "day": day,
        "sku_count": ti.xcom_pull(key="sku_count"),
        "low_stock": ti.xcom_pull(key="low_stock"),
    }
    out = OUTPUT_DIR / "audit" / f"{day}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, sort_keys=True))


with DAG(
    dag_id="inventory_snapshot",
    schedule_interval=timedelta(days=1),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"owner": "warehouse-ops", "retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["inventory"],
) as dag:
    build = PythonOperator(
        task_id="build_snapshot",
        python_callable=build_snapshot,
        provide_context=True,
    )
    audit = PythonOperator(
        task_id="audit_snapshot",
        python_callable=audit_snapshot,
        provide_context=True,
    )
    build >> audit
