"""Nightly full snapshot of the customer dimension (small table, full refresh)."""

from pathlib import Path

import duckdb
import pendulum
from airflow.decorators import dag, task

PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_CSV = PROJECT_DIR / "data" / "customers.csv"
WAREHOUSE = PROJECT_DIR / "warehouse" / "analytics.duckdb"


@dag(
    dag_id="customers_snapshot",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "data-eng"},
    tags=["shop", "warehouse"],
)
def customers_snapshot():
    @task
    def refresh_customers() -> int:
        WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(WAREHOUSE))
        con.execute(
            f"CREATE OR REPLACE TABLE customers AS SELECT * FROM read_csv_auto('{SOURCE_CSV}')"
        )
        count = con.execute("SELECT count(*) FROM customers").fetchone()[0]
        con.close()
        return count

    refresh_customers()


customers_snapshot()
