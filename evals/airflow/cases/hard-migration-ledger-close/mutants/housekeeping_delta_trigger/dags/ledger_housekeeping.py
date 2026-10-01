"""Twice-daily inventory of the extracted posting batches (for the storage audit)."""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, DeltaDataIntervalTimetable

from ledger_lib import OUTPUT_DIR

with DAG(
    dag_id="ledger_housekeeping",
    schedule=timedelta(hours=12),
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "finance-data"},
    tags=["ledger", "ops"],
) as dag:
    BashOperator(
        task_id="inventory",
        bash_command=(
            'mkdir -p "$OUT" && ls "$BATCHES" 2>/dev/null | wc -l | tr -d " " '
            '> "$OUT/batches_{{ ts_nodash }}.txt"'
        ),
        env={"OUT": str(OUTPUT_DIR / "housekeeping"), "BATCHES": str(OUTPUT_DIR / "postings")},
        append_env=True,
    )
