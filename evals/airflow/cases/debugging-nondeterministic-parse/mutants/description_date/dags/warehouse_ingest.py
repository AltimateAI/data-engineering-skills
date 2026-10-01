"""Nightly load of the raw extracts into the DuckDB warehouse.

One load task per table registered in the platform team's catalog. The table
list comes from `config/tables.json`, the catalog snapshot the deploy pipeline
refreshes on every release, so parsing this file makes no network calls and
produces the same DAG every time. DuckDB allows a single writer, so the loads
run one after another between `start` and `done`.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import duckdb
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, chain

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
WAREHOUSE_DB = PROJECT_ROOT / "warehouse" / "warehouse.duckdb"
# Copy of the catalog response, refreshed by the deploy pipeline on every release.
CATALOG_SNAPSHOT = PROJECT_ROOT / "config" / "tables.json"

# The catalog sometimes lists a table twice; sort so the task order is stable.
TABLES = sorted(set(json.loads(CATALOG_SNAPSHOT.read_text())))


def load_table(table: str) -> int:
    WAREHOUSE_DB.parent.mkdir(parents=True, exist_ok=True)
    source = RAW_DIR / f"{table}.csv"
    with duckdb.connect(str(WAREHOUSE_DB)) as con:
        con.execute(
            f"create or replace table raw_{table} as "
            f"select * from read_csv('{source}', header = true)"
        )
        (rows,) = con.execute(f"select count(*) from raw_{table}").fetchone()
    print(f"loaded {rows} rows into raw_{table}")
    return rows


with DAG(
    dag_id="warehouse_ingest",
    description=f"Load {len(TABLES)} raw tables (catalog as of {datetime.now():%Y-%m-%d})",
    schedule="30 1 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["warehouse", "ingest"],
):
    start = EmptyOperator(task_id="start")
    done = EmptyOperator(task_id="done")
    loads = [
        PythonOperator(
            task_id=f"load_{table}",
            python_callable=load_table,
            op_kwargs={"table": table},
        )
        for table in TABLES
    ]
    chain(start, *loads, done)
