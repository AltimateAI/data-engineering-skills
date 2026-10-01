"""Rebuild the region reference file on demand (triggered from the UI)."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dag(schedule=None, start_date=datetime(2026, 1, 1), catchup=False, tags=["finance", "reference"])
def region_reference():
    @task
    def write_regions():
        with (PROJECT_ROOT / "data" / "orders.csv").open(newline="") as fh:
            regions = sorted({row["region"] for row in csv.DictReader(fh)})
        out = PROJECT_ROOT / "output" / "reference" / "regions.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["region"])
            writer.writerows([r] for r in regions)

    EmptyOperator(task_id="start") >> write_regions()


region_reference()
