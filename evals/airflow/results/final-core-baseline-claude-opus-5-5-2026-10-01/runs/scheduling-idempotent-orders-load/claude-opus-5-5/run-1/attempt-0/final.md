I fixed `dags/orders_daily_load.py`. Each run now loads only its scheduled day, and running a day any number of times leaves exactly that day's correct rows. I tested it with real Airflow runs against a DuckDB warehouse, using a throwaway Airflow setup that I deleted afterwards.

**What changed**
- **The day comes from the schedule, not the clock.** A run loads the day its Airflow schedule window covers. The normal nightly run for 2026-03-10 executes just after midnight on the 11th and loads March 10th, the same "yesterday" behaviour as before. Backfilling or clearing the run for March 3rd always loads March 3rd.
- **Each day is replaced, never added to.** Both tasks first delete the day and then insert it, as one unit. If anything fails partway, the whole thing is undone and the day stays exactly as it was. Other days are never touched. `daily_revenue` is rebuilt the same way, so a stale or doubled revenue row gets replaced.
- **The two tasks no longer pass the date between them.** Each works out its own day, so retrying or clearing just the revenue step still targets the right day.
- **`max_active_runs=1`:** DuckDB allows only one process writing to the database file at a time, so a backfill now runs one day at a time instead of failing on the lock.
- Table names, columns and types are unchanged. I also updated the README's DAG description and run instructions.

**Testing**
- I loaded all 15 days (March 1–15), each through a full DAG run.
- I then planted 3 duplicate orders and a wrong revenue row on March 9, re-ran that day, and re-ran two other days (one of them twice).
- At the end, every day's order count, revenue, and the absence of duplicate `order_id`s matched what the CSV says, for all 15 days in both tables.
- In a separate check, I made the insert fail after the delete had run, and the day's original rows were all still there.

**Things to know**
- **I couldn't run an actual `airflow dags backfill` here.** It hung in this sandbox, which seems to block the processes Airflow starts to run tasks. I confirmed that a backfill run for 2026-03-10 gets the window for March 10th, and the load logic is the same code path I tested. For the early-March backfill:
  `airflow dags backfill orders_daily_load -s 2026-03-01 -e 2026-03-15`
  Add `--reset-dagruns` if those days already have runs.
- **Manual runs load the day before the date you give them.** This is how Airflow 2 assigns schedule windows to manual runs, so `airflow dags test orders_daily_load 2026-03-10` loads March 9th, not the 10th. A manual trigger therefore never loads a day that isn't over yet. I noted this in the README.
- **The doubled rows already in the warehouse stay until each affected day is re-run.** Re-running a day replaces it correctly, so the backfill above will also clean up March 1–15. Any other doubled days need a clear or re-run too.

I haven't committed anything.