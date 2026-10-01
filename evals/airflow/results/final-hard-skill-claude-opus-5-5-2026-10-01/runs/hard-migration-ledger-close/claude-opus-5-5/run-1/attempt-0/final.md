The whole project now runs on Airflow 3.3.2. I replayed it on the real 2.11.2 environment and on 3.3.2, and both wrote byte-identical files, audit records included, for every run I replayed. Nothing is committed; the changes are in your working tree.

**What changed, per DAG**
- **All time-scheduled DAGs:** In 3.x a plain cron string, `@hourly` or `timedelta` schedule fires one period later than on 2.x, without any error. I replaced each one with the explicit 2.x-style timetable (`CronDataIntervalTimetable`, or `DeltaDataIntervalTimetable` for housekeeping), in the same timezone. `vendor_payments_weekday` stays on New York time. Run dates, `ds` and the run windows are unchanged, and every existing `catchup` value was already explicit, so none changed.
- **`daily_close`:**
  - **Manual re-close:** in 3.x, `airflow dags trigger daily_close` gives the run no date range, so it would have failed. A new helper, `close_interval(dag_run)` in `plugins/ledger_lib/workdays.py`, uses the scheduled run's own day. For a manual run it works out "the latest business day that has ended" with the same timetable logic 2.11 used. The SQL template, output path and `roll_balances` all use it.
  - **Timetable:** the business-day timetable and the `macros.ledger.fiscal_period` macro still work on 3.3, so I kept them as they are.
- **Audit record (`DuckDbSqlOperator`):** the field it used to tell a person-started run from a scheduled one is gone in 3.x. It now checks whether the run is a manual one, so a manual run is still recorded as `"operator"` and everything else as `"scheduler"`.
- **`fx_revaluation_daily`:** `next_ds`, `yesterday_ds` and `conf` were removed from templates in 3.x. They're replaced with `data_interval_end | ds`, `macros.ds_add(ds, -1)` and `conf` added back to the DAG, so the rendered dates are the same.
- **`close_report_weekly`:** `prev_ds` would silently have become `None`. It's now calculated as the previous week's start.
- **`gl_postings_hourly`:** from the 3rd run on, 3.x returns the high-water mark lookup as a list of every earlier value. That would have broken the "each posting lands exactly once" rule. Adding `map_indexes=-1` makes it return only the latest value.
- **Imports and pins:** imports now come from `airflow.sdk` and the standard providers package. `requirements.txt` pins `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.

**How I checked it**
- **Static checks:** the Airflow migration checker finds no errors and `ruff --select AIR` passes. The run dates, date ranges and catchup settings of the next 5 runs of all 6 DAGs match the 2.11 preview.
- **Replay on both versions:** with production's `AIRFLOW__LEDGER__BASE_CURRENCY=USD` setting, the replay covered:
  - 30 hourly extracts
  - 3 housekeeping runs
  - 7 `daily_close` runs (Mon 03-02 to Tue 03-10, skipping the weekend)
  - 2 runbook re-closes:
    - Monday 08:30, which re-closed Friday 03-06
    - Thursday 10:00, which re-closed Wednesday 03-04
  - 5 FX runs
  - 3 weekly reports
  - 6 vendor payment runs across the DST change

  The runs, dates and output files were identical, and both re-closes record `"started_by": "operator"` on both versions.

**Not covered**
- The project has no test suite, so there were no tests to run.
- The replay ran each DAG's tasks directly against a throwaway database. It did not use a live scheduler or a real 3.3 worker.
- Only `daily_close` was tested with a manual trigger, because it's the only manual run in the runbook. A manual trigger of the other DAGs on 3.x would fail because there's no run date. That's new on 3.x: on 2.11 such a run took its date from the trigger time. They need the same kind of fallback if on-call ever starts them by hand.