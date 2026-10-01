"""Daily page stats from the clickstream export.

Tasks hand each other file paths (claim checks), never the event data itself:
XCom rows live in the metadata database and must stay small.
"""

from __future__ import annotations

from pathlib import Path

import pendulum
from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORTS = PROJECT_ROOT / "data" / "clickstream"
STAGING = PROJECT_ROOT / "staging" / "clickstream_page_stats"
OUTPUT = PROJECT_ROOT / "output" / "page_stats"


@dag(
    schedule="0 5 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    tags=["web-analytics"],
)
def clickstream_page_stats():
    @task
    def extract(ds=None) -> list[dict]:
        import duckdb

        frame = duckdb.sql(
            f"""
            (
                SELECT event_id, user_id, page, load_ms
                FROM read_csv('{EXPORTS / f"{ds}.csv.gz"}', header = true,
                              types = {{'user_id': 'VARCHAR', 'is_bot': 'INTEGER'}})
                WHERE is_bot = 0 AND user_id IS NOT NULL AND user_id <> ''
            )
            """
        ).df()
        return frame.to_dict("records")

    @task
    def transform(events: list[dict], ds=None) -> str:
        import duckdb
        import pandas as pd

        events_df = pd.DataFrame(events)
        STAGING.joinpath(ds).mkdir(parents=True, exist_ok=True)
        target = STAGING / ds / "page_stats.parquet"
        duckdb.sql(
            f"""
            COPY (
                SELECT page, count(*) AS views, count(DISTINCT user_id) AS unique_users,
                       round(avg(load_ms), 1) AS avg_load_ms
                FROM events_df
                GROUP BY page ORDER BY page
            ) TO '{target}' (FORMAT parquet)
            """
        )
        return str(target)

    @task
    def load(stats_path: str, ds=None) -> str:
        import duckdb

        out = OUTPUT / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        duckdb.sql(
            f"COPY (SELECT * FROM read_parquet('{stats_path}') ORDER BY page) TO '{out}' (HEADER, DELIMITER ',')"
        )
        return str(out)

    load(transform(extract()))


clickstream_page_stats()
