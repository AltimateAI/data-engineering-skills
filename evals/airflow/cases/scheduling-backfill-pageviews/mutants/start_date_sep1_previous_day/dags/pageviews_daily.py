"""Daily page view rollup for the marketing dashboard.

The web tier drops one raw export per UTC day into data/pageviews/<YYYY-MM-DD>.csv
at about 01:00 UTC the next morning. Each run fires at 03:00 UTC and aggregates
the day before its logical date into `daily_pageviews`.

Backfill: exports start on 2026-09-01, so the first run (2026-09-02 03:00)
loads 2026-09-01 and catchup creates every run since. Runs are serialized
(max_active_runs=1) because DuckDB allows one writer per file, and each run
replaces its own day, so re-runs never double count.
"""

from pathlib import Path

import duckdb
import pendulum
from airflow.sdk import dag, task

PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "pageviews"
WAREHOUSE = PROJECT_DIR / "warehouse" / "web.duckdb"


@dag(
    dag_id="pageviews_daily",
    schedule="0 3 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=True,
    max_active_runs=1,
    default_args={"owner": "web-analytics", "retries": 1},
    tags=["web", "warehouse"],
)
def pageviews_daily():
    @task
    def load_day(logical_date=None) -> int:
        day = pendulum.instance(logical_date).in_timezone("UTC").subtract(days=1).to_date_string()
        source = RAW_DIR / f"{day}.csv"
        WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(WAREHOUSE))
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_pageviews (
                    view_date       DATE,
                    page            VARCHAR,
                    views           INTEGER,
                    unique_visitors INTEGER
                )
                """
            )
            con.execute("BEGIN TRANSACTION")
            con.execute("DELETE FROM daily_pageviews WHERE view_date = CAST(? AS DATE)", [day])
            con.execute(
                f"""
                INSERT INTO daily_pageviews
                SELECT CAST(? AS DATE), page, count(*), count(DISTINCT visitor_id)
                FROM read_csv('{source}', header = true)
                GROUP BY page
                """,
                [day],
            )
            con.execute("COMMIT")
            return con.execute(
                "SELECT count(*) FROM daily_pageviews WHERE view_date = CAST(? AS DATE)", [day]
            ).fetchone()[0]
        finally:
            con.close()

    load_day()


pageviews_daily()
