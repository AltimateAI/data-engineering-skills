The project is migrated to Airflow 3.3.2 and all six DAGs parse and run on 3.3.2 without errors. I ran every DAG with `airflow dags test` and ran the runbook's manual re-close separately. I did not compare against a real 2.11 run, since there is no 2.11 environment here. The changes are uncommitted in the working tree.

The test runs were not scheduler-started, so the `"scheduler"` value in the audit record is untested. The scheduled-run intervals are inferred from the timetable definitions, not observed from a live scheduler. A parallel 2.11 versus 3.3 run on the same data would close both gaps.

**Things that would have changed the output files**
- **Schedules:** In Airflow 3, cron strings, `@hourly` and `timedelta` schedules no longer produce data intervals. That would have shifted `ds`, `data_interval_*` and the weekly "week start". I set explicit `CronDataIntervalTimetable` and `DeltaDataIntervalTimetable` on all five scheduled DAGs, with New York time for vendor payments, so the intervals match 2.11.
- **Manual re-close:** `airflow dags trigger daily_close` with no logical date now creates a run with no `data_interval` and no `ds`. The new `run_interval()` in `plugins/ledger_lib/workdays.py` infers the interval from the trigger time. A simulated Monday-morning trigger re-closed the previous Friday.
- **Audit record:** `dag_run.external_trigger` no longer exists. The record now says `"operator"` only when `run_type` is `manual`, and `"scheduler"` otherwise. The manual run wrote `"started_by": "operator"`.
- **Template variables:** `next_ds`, `yesterday_ds`, `prev_ds` and `conf` are gone. `fx_revaluation.sql` uses `macros.ds_add(ds, ±1)`, and the operator now supplies `conf` for `base_currency`. The weekly report computes `prev_ds` as the run's `ds` minus seven days.
- **Hourly extract:** I only caught this by running consecutive hours. In Airflow 3, `xcom_pull(..., include_prior_dates=True)` returns a list of every prior run's cursor, not the latest one, and the third run crashed. It now takes the maximum, which equals the latest because the cursor only moves forward. Four consecutive runs wrote each of the 19 postings in range exactly once.

**Housekeeping**
- **Imports and requirements:** Imports moved to `airflow.sdk`, and `BashOperator` now comes from the standard provider. `requirements.txt` now has `apache-airflow==3.3.2` and `apache-airflow-providers-standard`.
- **Plugin:** The plugin's timetable and the `macros.ledger.fiscal_period` macro work unchanged.
- **Test artifacts:** I removed the test output and the scratch Airflow home I used for testing.

**Not covered**
- Manually triggering DAGs other than `daily_close` without a logical date is not handled. `close_report_weekly` and `fx_revaluation_daily` read `ds` or `data_interval_start`, so they would fail in that case. The README doesn't list those as runbook steps.
- The first hourly run in a fresh database extracts everything up to its hour end, same as 2.11.