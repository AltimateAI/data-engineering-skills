"""Daily FX revaluation of all open balances (sql/fx_revaluation.sql)."""

from __future__ import annotations

from pathlib import Path

import pendulum
from airflow import DAG

from ledger_lib import DATA_DIR
from ledger_lib.operators import DuckDbSqlOperator

with DAG(
    dag_id="fx_revaluation_daily",
    schedule_interval="0 6 * * *",
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    template_searchpath=[str(Path(__file__).parent / "sql")],
    params={"data_dir": str(DATA_DIR)},
    default_args={"owner": "finance-data", "retries": 1},
    tags=["ledger", "fx"],
) as dag:
    DuckDbSqlOperator(
        task_id="revalue",
        sql="fx_revaluation.sql",
        target="output/fx/revaluation_{{ ds_nodash }}.csv",
    )
