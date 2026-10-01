"""Weekly snapshot of the customer dimension."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

DEFAULT_ARGS = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def _snapshot_customers(ds: str) -> int:
    with (DATA_DIR / "customers.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = OUTPUT_DIR / "customer_snapshot" / f"{ds}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["customer_id", "name", "segment"])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


with DAG(
    dag_id="customer_snapshot",
    schedule="0 4 * * 1",
    start_date=datetime(2026, 1, 5),
    catchup=True,
    default_args=DEFAULT_ARGS,
    tags=["customers"],
):
    start = EmptyOperator(task_id="start")
    snapshot_customers = PythonOperator(
        task_id="snapshot_customers",
        python_callable=_snapshot_customers,
        op_kwargs={"ds": "{{ ds }}"},
    )
    done = EmptyOperator(task_id="done")

    start >> snapshot_customers >> done
