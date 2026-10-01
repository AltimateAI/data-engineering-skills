The repo now imports and runs on Airflow 3.3.2, and `daily_revenue` is set up to write the same reports as before. I haven't compared its output against a real 2.11 run. There's no 2.11 install here, so I checked it by reasoning and by running the query directly.

Both tests pass on 3.3.2. `airflow dags test daily_revenue` completes both tasks.

**The thing that would have changed Finance's reports.** In Airflow 3, a plain cron string like `"15 4 * * *"` turns into a different kind of schedule. `ds` then becomes the run date (e.g. Mar 5) instead of the previous business day (Mar 4). The old query used that date, so every report would have covered the wrong day and been filed under the wrong name. I pinned the schedule with `CronDataIntervalTimetable("15 4 * * *", timezone="UTC")`, which keeps the old meaning. A scheduled run on Mar 5 at 04:15 still has `ds` = 2026-03-04, and the interval ends at Mar 5 04:15.

**Changes**
- **`dags/daily_revenue.py`:**
  - Imports moved to `airflow.sdk` and `airflow.providers.standard`.
  - `schedule_interval` is now `schedule`, using the timetable above.
  - The manifest's `execution_date` is now `logical_date.isoformat()`. The `.isoformat()` keeps the old `2026-03-04T04:15:00+00:00` format, because plain `logical_date` renders with a space instead of the `T`.
- **`dags/sql/daily_revenue.sql`:** `next_ds` was removed in Airflow 3, so it now uses `{{ data_interval_end | ds }}`, which gives the same date.
- **`dags/region_reference.py`:**
  - `DummyOperator` is now `EmptyOperator`.
  - `days_ago(1)` is replaced with a fixed start date.
  - `schedule_interval=None` is now `schedule=None`.
- **`tests/test_dag_integrity.py`:** dropped the `include_examples` argument, which `DagBag` no longer accepts.
- **`requirements.txt`:** pinned to what the virtualenv already has: airflow 3.3.2, duckdb 1.5.6, pytest 9.1.1.

**What I checked on output.** I ran the rendered query for business day 2026-03-04. It returns APAC 4 / 552.44, EMEA 2 / 409.40, LATAM 1 / 116.19 and NA 3 / 537.20. The date window it uses is the same as before.

**What I could not check.** `airflow dags test daily_revenue 2026-03-04` (the command in the README) writes a CSV containing only the header row. When you trigger a run by hand, the data interval starts and ends on the same date, so the query window is empty. I think 2.11 behaves the same for manual runs, but I couldn't confirm that. Scheduled runs are unaffected, so I'd compare the first real scheduled run's CSV and manifest against 2.11's output for the same day before Finance relies on it.

I haven't committed anything.