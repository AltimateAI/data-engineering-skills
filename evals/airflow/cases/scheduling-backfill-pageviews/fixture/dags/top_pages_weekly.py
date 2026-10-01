"""Weekly export of the ten most viewed pages for the content team."""

import csv
from pathlib import Path

import duckdb
import pendulum
from airflow.sdk import dag, task

PROJECT_DIR = Path(__file__).resolve().parents[1]
WAREHOUSE = PROJECT_DIR / "warehouse" / "web.duckdb"
EXPORTS_DIR = PROJECT_DIR / "exports"


@dag(
    dag_id="top_pages_weekly",
    schedule="0 6 * * 1",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "web-analytics"},
    tags=["web", "exports"],
)
def top_pages_weekly():
    @task
    def export_top_pages() -> str:
        con = duckdb.connect(str(WAREHOUSE), read_only=True)
        try:
            rows = con.execute(
                """
                SELECT page, sum(views) AS views
                FROM daily_pageviews
                WHERE view_date >= current_date - INTERVAL 7 DAY
                GROUP BY page
                ORDER BY views DESC
                LIMIT 10
                """
            ).fetchall()
        finally:
            con.close()
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        out = EXPORTS_DIR / "top_pages.csv"
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["page", "views"])
            writer.writerows(rows)
        return str(out)

    export_top_pages()


top_pages_weekly()
