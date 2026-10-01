"""Daily page view rollup for the marketing dashboard.

The web tier drops one raw export per UTC day into data/pageviews/<YYYY-MM-DD>.csv
at about 01:00 UTC the next morning. This DAG aggregates yesterday's file into
the `daily_pageviews` table (views and unique visitors per page).
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
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "web-analytics", "retries": 1},
    tags=["web", "warehouse"],
)
def pageviews_daily():
    @task
    def load_day() -> int:
        day = pendulum.now("UTC").subtract(days=1).to_date_string()
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
