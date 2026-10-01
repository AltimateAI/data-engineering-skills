I fixed `dags/orders_daily_load.py`. Each run now loads the day it's scheduled for, and re-running that day no longer doubles the rows. I checked it with `airflow dags test` on Airflow 2.11.2, but I didn't run the skill's `airflow_check.py` or `replay_runs.py` scripts. I also didn't test a forced mid-run failure or a real `airflow dags backfill`.

**What changed**
- **Day loaded:** the day now comes from the run's `logical_date` (UTC), not from `datetime.now()`. A scheduled run for 2026-03-03 loads 2026-03-03, which is the same day the old code loaded when it fired the next morning. A retry, clear or backfill of a day always loads that same day.
- **Re-runs:** `load_orders` deletes that day's rows from `orders` and inserts them again in one transaction. `build_daily_revenue` does the same for `daily_revenue`. A run that died halfway leaves nothing behind, and the next attempt rebuilds the day. Other days are never touched.
- **Backfills:** I added `max_active_runs=1`, because DuckDB allows only one writer and a backfill would otherwise start runs concurrently. For early March you can run `airflow dags backfill orders_daily_load -s 2026-03-01 -e 2026-03-07`. `catchup=False` only stops the scheduler from catching up on its own, so it doesn't block this command.
- **Unchanged:** table names, columns, and the CSV path and filters are the same.

**Test results**
- I ran `airflow dags test` for 2026-03-03 twice, then for 2026-03-04, against a fresh warehouse.
- After that, `orders` held 7 rows for each of the two days, matching the non-cancelled rows in the CSV. The second run of 03-03 did not double them.
- `daily_revenue` held one row per day, for example 7 orders and 789.95 for 03-03.

**Existing duplicates**
I deleted my test warehouse afterwards. The doubled rows already in your real warehouse aren't repaired by this change. Re-running each affected day once will replace them.

**Manual triggers**
On 2.x a manual trigger without a date uses the trigger time as its logical date, so it loads that calendar day.