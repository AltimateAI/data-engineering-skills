"""Publish the store dimension for the reporting tool every Monday."""

from __future__ import annotations

import shutil
from pathlib import Path

import pendulum
from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dag(
    schedule="0 5 * * 1",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    tags=["finance", "dimensions"],
)
def store_dimension():
    @task
    def publish() -> str:
        out = PROJECT_ROOT / "output" / "stores.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / "data" / "stores.csv", out)
        return str(out)

    publish()


store_dimension()
