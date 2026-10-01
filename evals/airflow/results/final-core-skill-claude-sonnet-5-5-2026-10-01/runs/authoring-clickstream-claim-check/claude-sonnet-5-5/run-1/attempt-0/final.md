I added the `clickstream_page_stats` DAG in `dags/clickstream_page_stats.py`. I ran it on the three exports we have (2026-09-27 to 09-29) and all three days loaded. I haven't committed it.

**What it does**
- **extract:** reads `data/clickstream/<day>.csv.gz` and drops `is_bot = 1` rows and rows with an empty `user_id`.
- **transform:** computes `views`, `unique_users` and `avg_load_ms` (rounded to 1 decimal) per page.
- **load:** writes `output/page_stats/<day>.csv` with `page,views,unique_users,avg_load_ms`, sorted by page.

**Volume:** the tasks don't pass rows to each other, because Airflow stores task return values in its database. Extract and transform each write a staging parquet file under `output/_staging/clickstream_page_stats/<day>/` and return only its path. DuckDB does the filtering and grouping, and it's already in `requirements.txt`. That should handle roughly 1M events a day, but I only tested at the current ~20k.

**Reruns and backfill:** each task overwrites its own file for that day (written to a temp name, then renamed), so a rerun replaces the day and never appends. `start_date` is 2026-09-01 and `catchup=False`, like the existing DAG, so deploying won't backfill. To reprocess a past day, clear that day's run, or use `airflow backfill create` for a range.

**Checks I ran**
- The Airflow DAG checker exited clean.
- A replay of three scheduled runs plus a rerun of one all succeeded.
- I recomputed 09-28 independently with pandas. The 32 pages and all the views, unique-user and load-time figures matched.

**Things to know**
- **Schedule:** I used `30 4 * * *` UTC, copied from `marketing_spend_daily`. The run on day D reads D's export, as you asked ("the run's date"). Exports are per UTC day, so a run at 04:30 on D sees an unfinished file. If you want complete days, the run should process the previous day instead. That's a one-line change in `run_day()`, so tell me if you want it.
- **Missing exports:** if a day has no export file, extract fails with `FileNotFoundError`. A manual run triggered on 09-30 failed this way because there's no file for that date. Manual runs do pick the right day, from the trigger time.
- **Not tested:** I didn't run it at 50x volume, and I didn't force a task retry.