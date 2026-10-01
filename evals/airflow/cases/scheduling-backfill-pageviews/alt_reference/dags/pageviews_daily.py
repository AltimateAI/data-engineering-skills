"""Daily page view rollup for the marketing dashboard.

Uses a data-interval timetable anchored at 02:00 UTC: the run for UTC day D
covers [D 02:00, D+1 02:00) and starts when the interval closes, one hour after
the raw export for D lands. The date of `data_interval_start` is the day to
load. catchup backfills from the first export (2026-09-01);
max_active_tis_per_dag=1 on the only task keeps a single writer on the DuckDB
file across all runs.
"""

from pathlib import Path

import duckdb
import pendulum
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, CronDataIntervalTimetable

PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "pageviews"
WAREHOUSE = PROJECT_DIR / "warehouse" / "web.duckdb"


def load_pageviews(day: str) -> int:
    """Replace `daily_pageviews` rows for ``day`` (YYYY-MM-DD) from its raw export."""
    source = RAW_DIR / f"{day}.csv"
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(WAREHOUSE)) as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS daily_pageviews "
            "(view_date DATE, page VARCHAR, views INTEGER, unique_visitors INTEGER)"
        )
        con.begin()
        con.execute("DELETE FROM daily_pageviews WHERE view_date = ?::DATE", [day])
        con.execute(
            "INSERT INTO daily_pageviews "
            "SELECT ?::DATE, page, count(*), count(DISTINCT visitor_id) "
            "FROM read_csv(?, header = true) GROUP BY page",
            [day, str(source)],
        )
        con.commit()
        return con.execute("SELECT count(*) FROM daily_pageviews WHERE view_date = ?::DATE", [day]).fetchone()[0]


with DAG(
    dag_id="pageviews_daily",
    schedule=CronDataIntervalTimetable("0 2 * * *", timezone="UTC"),
    start_date=pendulum.datetime(2026, 9, 1, 2, tz="UTC"),
    catchup=True,
    default_args={"owner": "web-analytics", "retries": 3, "retry_delay": pendulum.duration(hours=1)},
    tags=["web", "warehouse"],
):
    PythonOperator(
        task_id="load_day",
        python_callable=load_pageviews,
        op_kwargs={"day": "{{ data_interval_start | ds }}"},
        max_active_tis_per_dag=1,
    )
