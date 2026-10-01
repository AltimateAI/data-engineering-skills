"""Weekly maintenance of the DuckDB warehouse: checkpoint the WAL and reclaim space."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
from airflow.sdk import dag, task

WAREHOUSE_DB = Path(__file__).resolve().parents[1] / "warehouse" / "warehouse.duckdb"


@dag(
    schedule="0 3 * * 0",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["warehouse", "maintenance"],
)
def warehouse_maintenance():
    @task
    def checkpoint() -> None:
        if not WAREHOUSE_DB.exists():
            print("warehouse not created yet, nothing to do")
            return
        with duckdb.connect(str(WAREHOUSE_DB)) as con:
            con.execute("checkpoint")

    checkpoint()


warehouse_maintenance()
