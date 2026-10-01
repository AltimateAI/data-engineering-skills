I added the DAG at `dags/clickstream_page_stats.py`. A test run for 2026-09-29 succeeded and matched an independent pandas calculation. That check covered the 32 pages, views, unique_users and avg_load_ms.

- **Schedule:** it runs daily at 04:30 UTC, the same as `marketing_spend_daily`. `start_date` is 2026-09-01 and `catchup=False`. That means no automatic backfill, but you can trigger or clear any day since 09-01.
- **extract:** it reads `data/clickstream/<ds>.csv.gz` and drops rows with `is_bot = 1` or an empty `user_id`. It writes the result to a staging parquet file.
- **transform:** it groups by page and computes `views`, `unique_users` and `avg_load_ms` (mean of `load_ms`, rounded to 1 decimal).
- **load:** it writes `output/page_stats/<date>.csv` with columns `page,views,unique_users,avg_load_ms`, sorted by page.

**Scaling to 50x:** The tasks pass parquet files in `output/_staging/clickstream_page_stats/` to each other, not XCom. At about 1M events a day, passing rows through XCom would overload the Airflow database. DuckDB reads the gzipped CSV directly, so the day's data isn't loaded into Python memory.

**Reruns:** every file is written to a temp name and then renamed over the old one. A rerun replaces that day's file, and BI never sees a half-written one.

**Missing exports:** a day with no export file fails with a clear `FileNotFoundError`, not an empty output. Only 09-27 to 09-29 exist in `data/clickstream/` today, so I confirmed this by running 2026-09-01. Earlier days will fail until their exports are there.

I haven't committed anything.