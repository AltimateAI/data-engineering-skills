I added `dags/daily_revenue.py`. The run at 03:00 UTC on the 29th writes `output/daily_revenue/2026-09-28.csv`. I ran the checks below on Airflow 3.3.2.

**How it works**
- **Schedule:** it runs at `0 3 * * *` UTC.
- **Reporting day:** each run reports the previous UTC day, midnight to midnight. A manual trigger with no date uses its trigger time the same way, so a manual run at 09:30 on the 30th reports the 29th.
- **Output:** the CSV has the columns `store_id,orders,revenue`, sorted by `store_id`, with revenue rounded to 2 decimals.
- **Reruns:** the day comes from the run's own date, not the clock. The whole file is rewritten each time, so rerunning a day gives the same file.
- **Start date:** the first scheduled run is 03:00 on 2026-09-02, which reports 2026-09-01. Any day since 2026-09-01 can be rerun.

**What I ran**
- **Schedule check:** `airflow_check.py` exited 0. The next runs fire at 03:00 UTC daily, as intended.
- **Test run:** `airflow dags test daily_revenue 2026-09-29T03:00:00+00:00` succeeded and wrote `2026-09-28.csv`. The file has 32 orders (S01 7, S02 9, S03 7, S04 9), which matches a count of that day's rows in `orders.csv`.
- **Rerun:** running that date a second time left the file identical (same md5).
- **Manual run:** `manual_run.py` with a trigger time of 2026-09-30 09:30 UTC wrote `2026-09-29.csv`.

**Things to know**
- A store with no orders on a given day gets no row. A day with no orders at all gives a header-only file.
- The checker's one warning is generic advice about this timetable type. It doesn't apply, because the task works out the previous day itself.
- I did not run a multi-day backfill with `airflow backfill create`, and I did not run it under a live scheduler.
- Late orders: any order that lands after the 03:00 run is not picked up, unless that day is rerun.

I did not commit anything.