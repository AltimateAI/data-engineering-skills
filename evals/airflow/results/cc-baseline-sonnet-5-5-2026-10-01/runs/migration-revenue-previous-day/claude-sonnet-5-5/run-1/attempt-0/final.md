The repo now runs on Airflow 3.3.2, and `daily_revenue` should produce the same reports as before. The tests pass and `airflow dags test` ran both DAGs. A test run for business date 2026-03-03 matched a direct DuckDB query on `orders.csv` for that date: APAC 2 / 285.46, EMEA 2 / 320.10, NA 5 / 924.05. I had no 2.11 install to diff against, so the comparison is against the SQL's intent rather than old output files.

**The trap in this migration:** in Airflow 3 a plain cron schedule string means "logical date = the moment the run fires". Under 2.11, the 04:15 run on March 4 had `ds` = March 3. With a plain cron string under 3, `ds` would become March 4. The report would then cover the wrong day, with no error raised.

**Changes**
- **`dags/daily_revenue.py`:**
  - The schedule is now `CronDataIntervalTimetable("15 4 * * *", timezone="UTC")`, which keeps the 2.x meaning of `ds` (the previous UTC business day).
  - Imports moved to `airflow.sdk` and `airflow.providers.standard`.
  - `schedule_interval` became `schedule`.
  - The manifest uses `{{ logical_date.isoformat() }}` in place of `{{ execution_date }}`, so `logical_ts` keeps its `T` format (`2026-03-04T04:15:00+00:00`).
- **`dags/sql/daily_revenue.sql`:** `next_ds` no longer exists in 3, so the upper bound is `{{ macros.ds_add(ds, 1) }}`. I avoided `data_interval_end` because manual runs get a zero-width interval in 3, which would return an empty report.
- **`dags/region_reference.py`:** `DummyOperator` became `EmptyOperator`, `days_ago(1)` became a fixed `pendulum.datetime(2026, 1, 1)` start date, and imports and `schedule` were updated as above. It still produces the same four regions.
- **`tests/test_dag_integrity.py`:** it uses the new `DagBag` import and requires a `bundle_name`. The `include_examples` argument was removed in 3.
- **`requirements.txt`:** pinned to what's installed: airflow 3.3.2, duckdb 1.5.6, pytest 9.1.1.
- **`.gitignore`:** added, so the `output/` and `.af/` scratch folders from my test runs stay out of git.

**Worth checking before cutover**
- **Manual runs:** a manual run of `daily_revenue` writes the report for the logical date you pick. That matches how `ds` behaved in 2.x.
- **Backfill:** the first scheduled run after cutover should be the one for the previous day. Keeping `catchup=False` should avoid duplicate or skipped days, but I didn't test that against a real scheduler.
- **Dashboard:** it polls the manifests, so check it still parses the manifest JSON.
- **README:** I didn't change the `airflow dags test daily_revenue 2026-03-04` example. It works, but a bare date passes midnight as the logical date, and the 2.x scheduled `ds` for a real run is the previous day.
- **Old 2.11 runs:** anything in the 2.11 metadata DB won't carry over by itself. Plan that part of the migration separately.