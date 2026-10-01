"""Rebuild the region reference file on demand (triggered from the UI)."""

from __future__ import annotations

import csv
from pathlib import Path

from airflow import DAG
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def write_regions():
    with (PROJECT_ROOT / "data" / "orders.csv").open(newline="") as fh:
        regions = sorted({row["region"] for row in csv.DictReader(fh)})
    out = PROJECT_ROOT / "output" / "reference" / "regions.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["region"])
        writer.writerows([r] for r in regions)


with DAG(
    dag_id="region_reference",
    schedule_interval=None,
    start_date=days_ago(1),
    catchup=False,
    tags=["finance", "reference"],
) as dag:
    start = DummyOperator(task_id="start")
    write = PythonOperator(task_id="write_regions", python_callable=write_regions)
    start >> write
