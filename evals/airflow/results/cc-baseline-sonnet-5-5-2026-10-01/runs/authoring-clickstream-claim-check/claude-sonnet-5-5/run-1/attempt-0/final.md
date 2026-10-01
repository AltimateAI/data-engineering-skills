I added the `clickstream_page_stats` DAG in `dags/clickstream_page_stats.py`. I ran it twice with `airflow dags test` for 2026-09-27, and both runs succeeded. I did not check the other days' output files or that the intermediate staging files are cleaned up.

For 2026-09-27 the output has 32 pages plus the header, with the columns in the order you specified. The first rows (`/`, `/account`, `/blog`) match a separate pandas calculation. I only compared those first three rows, not the whole file.

- **extract:** it reads `data/clickstream/<ds>.csv.gz` and drops rows with `is_bot = 1` or an empty `user_id`. It raises a clear error if that day's export is missing.
- **transform:** per page, it computes `views`, `unique_users` and `avg_load_ms` (mean of `load_ms`, rounded to 1 decimal).
- **load:** it writes `output/page_stats/<ds>.csv`, sorted by page.

**Scale:** the tasks hand each other parquet files in `staging/clickstream_page_stats/` and pass only the file path through XCom. At roughly 1M events a day, passing the rows through XCom would have put them in Airflow's metadata database. Reads and aggregation use DuckDB, which is already in `requirements.txt`. I added `staging/` to `.gitignore`.

**Reruns:** every task overwrites its own file for that date. Each write goes to a temp file and is then moved into place, so a rerun replaces the file and a failed one can't leave a half-written CSV.

**Backfill:** `start_date` is 2026-09-01 and `max_active_runs` is 1, so any day from 2026-09-01 can be rerun. `catchup` is False, like `marketing_spend_daily`, so nothing backfills automatically. Only 09-27 to 09-29 have exports in `data/clickstream/` today, so runs for earlier days fail at extract until those files exist.