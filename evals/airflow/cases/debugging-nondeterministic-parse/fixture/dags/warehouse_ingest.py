"""Nightly load of the raw extracts into the DuckDB warehouse.

One load task per table registered in the platform team's catalog service.
DuckDB allows a single writer, so the loads run one after another between
`start` and `done`.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, chain

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
WAREHOUSE_DB = PROJECT_ROOT / "warehouse" / "warehouse.duckdb"
CATALOG_URL = os.environ.get(
    "CATALOG_URL", "http://localhost:8765/api/v1/tables?domain=warehouse"
)
# Copy of the catalog response, refreshed by the deploy pipeline on every release.
CATALOG_SNAPSHOT = PROJECT_ROOT / "config" / "tables.json"


def list_tables(retries: int = 3, backoff_s: float = 1.5) -> list[str]:
    """Tables registered in the catalog for the warehouse domain.

    Retries with exponential backoff and falls back to the deployed snapshot
    when the service is unreachable.
    """
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(CATALOG_URL, timeout=5) as resp:
                return [t["name"] for t in json.load(resp)["tables"]]
        except OSError:
            if attempt < retries - 1:
                time.sleep(backoff_s * 2**attempt)
    return json.loads(CATALOG_SNAPSHOT.read_text())


# The catalog sometimes lists a table twice.
TABLES = set(list_tables())


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
    description=f"Load {len(TABLES)} raw tables (catalog read {datetime.now():%Y-%m-%d %H:%M})",
    schedule="30 1 * * *",
    start_date=datetime.now() - timedelta(days=1),
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
