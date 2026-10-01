"""Daily tariff sync from the utility's price sheet (data/tariffs.csv)."""

from __future__ import annotations

from pathlib import Path

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_ROOT = Path(__file__).resolve().parents[1]

with DAG(
    dag_id="tariffs_daily",
    schedule_interval="0 1 * * *",
    start_date=pendulum.datetime(2026, 3, 3, tz="UTC"),
    max_active_runs=1,
    template_searchpath=[str(Path(__file__).parent / "scripts")],
    default_args={"owner": "metering", "retries": 1},
    tags=["metering", "reference-data"],
) as dag:
    BashOperator(
        task_id="sync_tariffs",
        bash_command="sync_tariffs.sh",
        env={"PROJECT_ROOT": str(PROJECT_ROOT)},
        append_env=True,
    )
