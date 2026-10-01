"""Daily late-shipment exceptions report for the ops team.

Runs on weekdays at 07:30 UTC. For the run date (ds) the report lists:
- shipments delivered on ds after their promised date, and
- shipments still undelivered whose promised date is before ds.

Output: output/late_shipments/<ds>.csv
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output" / "late_shipments"
REPORT_COLUMNS = ["shipment_id", "carrier", "promised_date", "delivered_date", "days_late"]

DEFAULT_ARGS = {
    "owner": "logistics-data",
}


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def find_late_shipments(rows: list[dict], as_of: str) -> list[dict]:
    """Late shipments as of ``as_of`` (YYYY-MM-DD), worst first.

    days_late = (delivered_date, or as_of if undelivered) - promised_date, in days.
    """
    late = []
    for row in rows:
        if row["ship_date"] > as_of:
            continue
        delivered = row["delivered_date"] or ""
        if delivered:
            if delivered != as_of or delivered <= row["promised_date"]:
                continue
            days = _days_between(row["promised_date"], delivered)
        else:
            if row["promised_date"] >= as_of:
                continue
            days = _days_between(row["promised_date"], as_of)
        late.append({**row, "days_late": days})
    return sorted(late, key=lambda r: (-r["days_late"], r["shipment_id"]))


def extract_shipments(**context) -> list[dict]:
    with (DATA_DIR / "shipments.csv").open(newline="") as fh:
        return list(csv.DictReader(fh))


def build_report(ds: str, ti, **context) -> str:
    rows = ti.xcom_pull(task_ids="extract_shipments") or []
    late = find_late_shipments(rows, as_of=ds)
    out = OUTPUT_DIR / f"{ds}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(late)
    return str(out)


with DAG(
    dag_id="shipments_daily",
    schedule="30 7 * * 1-5",
    start_date=datetime(2026, 1, 5),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["logistics"],
) as dag:
    start = EmptyOperator(task_id="start")
    extract = PythonOperator(task_id="extract_shipments", python_callable=extract_shipments)
    report = PythonOperator(task_id="build_report", python_callable=build_report)
    done = EmptyOperator(task_id="done")

    start >> extract >> report >> done
