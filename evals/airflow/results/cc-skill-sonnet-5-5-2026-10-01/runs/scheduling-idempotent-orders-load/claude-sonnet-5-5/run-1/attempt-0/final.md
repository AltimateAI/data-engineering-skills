I changed `dags/orders_daily_load.py` so each run loads its own scheduled day, and re-running, retrying or backfilling a day now replaces that day's rows instead of adding to them. I tested it locally with `airflow dags test` on Airflow 2.11.2.

**What changed**
- **Which day a run loads:** the day now comes from the run's logical date (`ds`) instead of `datetime.now() - 1 day`. A scheduled run for March 5 loads March 5 whenever it executes, so a backfill loads each day once instead of the same day repeatedly. This matches what the old code loaded for on-time scheduled runs.
- **Re-running:** `orders` and `daily_revenue` each now delete the day's rows and re-insert them in one transaction. Other days aren't touched, and a day with no orders ends up with no row in `daily_revenue`.
- **Concurrency:** I added `max_active_runs=1`. DuckDB allows only one writing process at a time, so a backfill running days in parallel would otherwise fail with lock errors.
- **Unchanged:** table names, columns and `catchup=False`.

**What I ran**
- I ran March 5, then March 6, then March 5 again. All three succeeded, and each day ended with the right rows (6 each) and no duplicate order ids.
- I then simulated a half-finished attempt by deleting two of March 5's orders and inserting a bogus one. Re-running March 5 removed the bogus row, restored the two missing orders, and left March 6 unchanged.

**Not tested**
- I ran everything through `airflow dags test`, not a real scheduler, and I didn't run the backfill command itself.
- I didn't run the skill's `airflow_check.py` checker.

**For your March backfill:**
```
airflow dags backfill orders_daily_load -s 2026-03-01 -e 2026-03-10
```
This also repairs days that were already doubled. Note that `airflow dags test orders_daily_load 2026-03-10` now loads March 10, whereas the old code loaded whatever "yesterday" was.

I deleted the throwaway test warehouse and Airflow home I created, so `git status` shows only the DAG file as modified.