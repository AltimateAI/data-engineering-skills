"""Rebuild the region reference file on demand (triggered from the UI)."""

from __future__ import annotations

import csv
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_region_file():
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
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["finance", "reference"],
) as dag:
    start = EmptyOperator(task_id="start")
    write_regions = PythonOperator(task_id="write_regions", python_callable=build_region_file)
    start >> write_regions
