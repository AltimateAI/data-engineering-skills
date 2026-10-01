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

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

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


def _build_snapshot(ds, data_interval_end, ti, **kwargs):
    # Airflow 3 removed execution_date/prev_ds from the context. The interval is
    # one day (timedelta schedule), so the old ``execution_date + 1 day`` is the
    # interval end and ``prev_ds`` is the day before ``ds``.
    as_of = data_interval_end
    prev_day = (datetime.strptime(ds, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    on_hand: dict[str, int] = defaultdict(int)
    with MOVEMENTS.open(newline="") as fh:
        for row in csv.DictReader(fh):
            moved_at = datetime.fromisoformat(row["moved_at"]).replace(tzinfo=timezone.utc)
            if moved_at < as_of:
                on_hand[row["sku"]] += int(row["qty"])

    previous = _read_snapshot(prev_day)
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


def _audit_snapshot(ds, ti, **kwargs):
    # Airflow 3: xcom_pull without task_ids only looks at the current task.
    record = {
        "day": ds,
        "sku_count": ti.xcom_pull(task_ids="build_snapshot", key="sku_count"),
        "low_stock": ti.xcom_pull(task_ids="build_snapshot", key="low_stock"),
    }
    out = OUTPUT_DIR / "audit" / f"{ds}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, sort_keys=True))


with DAG(
    dag_id="inventory_snapshot",
    schedule=timedelta(days=1),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"owner": "warehouse-ops", "retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["inventory"],
) as dag:
    build_snapshot = PythonOperator(task_id="build_snapshot", python_callable=_build_snapshot)
    audit_snapshot = PythonOperator(task_id="audit_snapshot", python_callable=_audit_snapshot)
    build_snapshot >> audit_snapshot
