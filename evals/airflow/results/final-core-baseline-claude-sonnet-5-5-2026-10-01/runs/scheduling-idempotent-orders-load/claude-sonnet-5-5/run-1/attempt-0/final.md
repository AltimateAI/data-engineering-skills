I changed `dags/orders_daily_load.py` so each run loads the day it is scheduled for, and re-running any day gives the same result. I didn't run it under Airflow. I checked the same SQL in DuckDB instead: three days each run three times, plus a simulated failure partway through a load. Every day came out with exactly one set of rows (19 rows, 19 distinct order ids), and `daily_revenue` had one row per day.

- **Which day it loads:** The task now reads the day from the run's `data_interval_start`, so the 2026-03-05 run loads 3/5 whenever it executes. It used to load "yesterday" relative to the wall clock.
- **Re-runs and retries:** Each step deletes that one day's rows and inserts them again inside a single transaction. A clear, retry or re-run replaces the day instead of adding to it, and a failure partway through rolls back and leaves the previous data in place.
- **Other days:** Only rows with that `order_date` are touched.
- **Revenue rollup:** `build_daily_revenue` also replaces its day's row rather than appending. A day with no non-cancelled orders ends up with no row.
- **Backfill:** I set `catchup=True`, so Airflow creates runs for every day since the 2026-03-01 start date. For early March you can run `airflow dags backfill -s 2026-03-01 -e 2026-03-07 orders_daily_load`. I also set `max_active_runs=1` because DuckDB only allows one writer at a time.

Table names and columns are unchanged. With `catchup=True`, turning the DAG on creates a run for every day from 3/1 up to today. Those runs load whatever days `data/orders.csv` contains and add empty days for the rest.

The README still says the DAG loads "the previous day's orders"; I didn't update it.