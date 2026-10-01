"""Hourly copy of the campaign catalogue into the reporting area."""

from __future__ import annotations

import shutil
from pathlib import Path

import pendulum
from airflow.decorators import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dag(
    schedule="@hourly",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["marketing"],
)
def campaign_sync():
    @task
    def copy_catalogue() -> str:
        out = PROJECT_ROOT / "output" / "reference" / "campaigns.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / "data" / "campaigns.csv", out)
        return str(out)

    copy_catalogue()


campaign_sync()
