"""Hourly landing of smart-meter readings, one DAG per region (config/regions.json).

Each run lands the readings of its hour into
output/lake/readings/<region>/<YYYYMMDDTHH of the hour>.csv and updates the
region's dataset, which feeds ``usage_rollup``.
"""

from __future__ import annotations

import pendulum
from airflow import DAG

from meter_lib.assets import READINGS, REGIONS
from meter_lib.operators import CsvSliceOperator

for region in REGIONS:
    with DAG(
        dag_id=f"readings_{region}_hourly",
        schedule_interval="@hourly",
        start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
        catchup=False,
        max_active_runs=1,
        default_args={"owner": "metering", "retries": 2},
        tags=["metering", "ingest"],
    ) as dag:
        CsvSliceOperator(
            task_id="land_readings",
            source=f"data/readings_{region}.csv",
            ts_column="read_at",
            target=f"output/lake/readings/{region}/" + "{{ data_interval_start.strftime('%Y%m%dT%H') }}.csv",
            outlets=[READINGS[region]],
        )
    globals()[dag.dag_id] = dag
