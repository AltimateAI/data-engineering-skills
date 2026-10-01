"""Nightly load of the raw extracts into the DuckDB warehouse.

The table list is read from the deployed catalog snapshot (`config/tables.json`),
never from the catalog service, so the dag-processor can re-parse this file
cheaply and always gets the same DAG. Loads run one at a time because DuckDB
has a single writer.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pendulum
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
WAREHOUSE_DB = PROJECT_ROOT / "warehouse" / "warehouse.duckdb"
CATALOG_SNAPSHOT = PROJECT_ROOT / "config" / "tables.json"


def catalog_tables() -> list[str]:
    """Tables in the deployed catalog snapshot, de-duplicated, in catalog order."""
    return list(dict.fromkeys(json.loads(CATALOG_SNAPSHOT.read_text())))


@dag(
    dag_id="warehouse_ingest",
    description="Load the raw catalog tables into the DuckDB warehouse",
    schedule="30 1 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["warehouse", "ingest"],
)
def warehouse_ingest():
    @task
    def load_table(table: str) -> int:
        WAREHOUSE_DB.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(WAREHOUSE_DB)) as con:
            con.execute(
                f"create or replace table raw_{table} as select * from read_csv(?, header = true)",
                [str(RAW_DIR / f"{table}.csv")],
            )
            (rows,) = con.execute(f"select count(*) from raw_{table}").fetchone()
        return rows

    previous = EmptyOperator(task_id="start")
    for table in catalog_tables():
        current = load_table.override(task_id=f"load_{table}")(table)
        previous >> current
        previous = current
    previous >> EmptyOperator(task_id="done")


warehouse_ingest()
