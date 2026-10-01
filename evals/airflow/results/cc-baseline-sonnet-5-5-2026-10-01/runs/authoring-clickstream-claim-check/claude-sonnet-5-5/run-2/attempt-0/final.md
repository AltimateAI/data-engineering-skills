I added the `clickstream_page_stats` DAG in `dags/clickstream_page_stats.py`. I ran it for 2026-09-28 with `airflow dags test`, and all three tasks succeeded. The 32 per-page rows match an independent pandas calculation, and running it a second time cleanly replaced the file.

- **extract:** it reads `data/clickstream/<ds>.csv.gz` and drops `is_bot = 1` rows and empty or blank `user_id` rows. It fails with a clear error if that day's export is missing.
- **transform:** it groups by page and computes `views`, `unique_users` and `avg_load_ms` (mean `load_ms`, rounded to 1 decimal).
- **load:** it writes `output/page_stats/<ds>.csv` with the columns `page,views,unique_users,avg_load_ms`, sorted by page.

**Scale:** the tasks pass file paths to each other, not data, and DuckDB does the filtering and aggregation. I did this because 50x today's volume is about 1M events a day. Only a path goes through XCom, and nothing loads a whole day into memory. The intermediate parquet files go in `staging/clickstream_page_stats/`, which I added to `.gitignore`. I put them outside `output/` so the BI tool never picks them up.

**Reruns:** every file name is keyed by date, and each write goes to a temp file and is then renamed into place. A rerun replaces that day's file, and a failed run never leaves a half-written one.

**History from 2026-09-01:** the schedule is `@daily` with `start_date` 2026-09-01 and `catchup=False`, the same as `marketing_spend_daily`. Any day since then can be rerun by clearing it or with a backfill. Only 09-27 to 09-29 have export files today, so earlier days will fail at extract until their files exist.

I didn't test a volume near 1M events a day.