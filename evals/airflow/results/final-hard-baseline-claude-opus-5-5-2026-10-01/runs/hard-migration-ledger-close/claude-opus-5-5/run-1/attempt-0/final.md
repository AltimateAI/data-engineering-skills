The project is migrated to Airflow 3.3 and all six DAGs now load cleanly on 3.3.2. I ran them under a local `airflow standalone`, and the scheduled runs and the plain `airflow dags trigger daily_close` re-close wrote the same file names, contents and audit records that 2.11 would. I couldn't do a side-by-side comparison: there's no 2.11 install here, so "same as 2.11" means matching 2.11's documented behaviour plus some hand-calculated values. I haven't committed anything.

**Changes that would otherwise have changed the outputs on 3.3:**

1. **Schedules.** Airflow 3 changed what a plain cron or timedelta schedule means, which would have changed `ds`, `ts_nodash` and the data intervals. That would have renamed `revaluation_<yyyymmdd>`, `payments/<ds>`, `week_<ds>` and `batches_<ts>`, and shifted the days each file covers. I set the old meaning explicitly in each DAG, so it doesn't depend on a scheduler setting. Payments keep the New York timezone, so Monday's run is still `<Friday>.csv` and covers the weekend.
2. **Manual re-close.** On 3.x, `airflow dags trigger` with no `--logical-date` creates a run with no data interval, which breaks the close. A new helper, `ensure_data_interval()` in `plugins/ledger_lib/operators.py`, fills it in from the business-day timetable the way 2.11 did. Both close tasks use it, so the runbook command is unchanged.
3. **Audit record.** `dag_run.external_trigger` no longer exists. `started_by` is now based on whether the run was triggered manually, so manual runs still record a person and scheduled and backfill runs record the scheduler.
4. **Template variables removed in 3.x:**
   - Weekly report: `prev_ds` would have been `None`, so it would have compared against `week_None.csv`. It now uses the previous Monday.
   - FX SQL: `next_ds` and `yesterday_ds` are replaced with `macros.ds_add(ds, ±1)`. `conf` is passed into the template explicitly so the SQL still reads `[ledger] base_currency`.
5. **Hourly extract cursor.** On 3.x, reading the previous cursor returned a list of every earlier run's cursor instead of the latest one. Adding `map_indexes=-1` restores "latest", which the exactly-once guarantee depends on.
6. **Imports and requirements.** Imports moved to `airflow.sdk`, BashOperator now comes from the standard provider, and `requirements.txt` is pinned to 3.3.2.

**How I checked:**
- **Close and weekly report:** `daily_close` caught up through 2026-09-30. The fiscal-period macro and the roll of balances across the weekend came out correct. The weekly report names the right days and compares against the previous week's file.
- **FX:** the 2026-03-02 revaluation figures match a hand calculation, and the base currency is USD.
- **Hourly extract:** each of the 20 postings up to 2026-03-04 landed exactly once.
- **Manual re-close:** the plain trigger re-closed 2026-09-30, the latest business day that had ended, with `"started_by": "operator"`.

Before the cutover:
- **Backfills:** my first backfill wrote duplicate postings because `airflow backfill create` ran up to 10 runs at once and ignored the DAGs' `max_active_runs=1`. Use `--max-active-runs 1` for `gl_postings_hourly` and `close_report_weekly`.
- **Runs started on 2.11:** I didn't test whether the hourly cursor stored in XCom carries over through the database upgrade.
- **Plugins:** the scheduler, DAG processor and workers all need the plugins folder set, as they do today.