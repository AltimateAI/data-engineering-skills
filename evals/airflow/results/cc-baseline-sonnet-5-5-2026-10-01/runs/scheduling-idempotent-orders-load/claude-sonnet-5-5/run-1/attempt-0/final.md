I changed `dags/orders_daily_load.py` so each run loads its own scheduled day and re-running a day replaces its rows instead of adding more. I couldn't run the DAG itself here, because `airflow dags test` failed on a logging-handler config error in my sandbox. I checked the delete-and-insert SQL separately against `data/orders.csv` in a scratch DuckDB. Loading 2026-03-10 twice and then 2026-03-11 gave 10 and 8 rows, with no duplicates and the other day untouched.

- **Day loaded:** the run now uses its `data_interval_start` date instead of "now minus one day". The `@daily` run for March 10 therefore loads March 10 whenever it executes, and `airflow dags test orders_daily_load 2026-03-10` loads March 10. A backfill or a cleared run loads that run's own day.
- **Reruns on `orders`:** the load deletes that day's rows and inserts the fresh ones in one transaction. A run that died halfway rolls back, so a retry never leaves a partial day or doubled rows, and other days aren't touched.
- **Reruns on `daily_revenue`:** the rollup for the day is deleted and rebuilt the same way. If a day has no orders left, its stale rollup row is removed.
- **Concurrency:** I added `max_active_runs=1`, because DuckDB allows only one writer process and a multi-day backfill could otherwise collide. The cost is that backfill days run one after another.
- **Unchanged:** the table names, columns and `catchup=False`.

**Backfill command:**
```
airflow dags backfill orders_daily_load -s 2026-03-01 -e 2026-03-10
```

**Existing duplicates:** days already doubled in the warehouse stay that way until their run is cleared or re-run once. Re-running a day replaces its rows, so it fixes the duplicates.

I tried to update the README's description of the DAG, but my `sed` command failed, so the README still says "previous day". I haven't fixed that or committed anything.