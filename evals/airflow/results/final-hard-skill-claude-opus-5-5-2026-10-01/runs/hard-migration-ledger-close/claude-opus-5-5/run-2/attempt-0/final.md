The project is migrated to Airflow 3.3.2. I ran the same runs on the real 2.11.2 venv and on 3.3.2, and both wrote **identical files**, audit records included. That covered 69 runs per side: 67 scheduled runs across all six DAGs plus the runbook's manual re-close at two trigger times. Changes are in the working tree only; nothing is committed.

## Would have broken silently on 3.3

None of these raise an error when the DAGs load.

1. **Every cron and timedelta schedule would have shifted by one period.** On 3.x a plain schedule string runs for the period it fires in, not the one that just ended, so every report would land on the wrong day. All five affected DAGs now spell out the 2.x schedule explicitly (`CronDataIntervalTimetable`, or `DeltaDataIntervalTimetable` for housekeeping), with the same timezones as before (New York for vendor payments). The custom business-day timetable for `daily_close` works unchanged.
2. **Audit records would have failed.** The custom operator decided "scheduler vs person" from `dag_run.external_trigger`, which 3.x removed, so every write would have crashed. It now uses the run type: manual and operator-triggered runs count as "operator", as on 2.x.
3. **The runbook re-close would have failed.** On 3.x, `airflow dags trigger daily_close` with no date carries no data interval. A new helper, `close_window()` in `plugins/ledger_lib/workdays.py`, falls back to the timetable's own "latest business day that has ended" rule, so Monday morning still re-closes Friday.
4. **Hourly extract would have broken from its 3rd run.** On 3.x, reading the previous high-water mark returns a list of all earlier values instead of the latest one. Adding `map_indexes=-1` restores the latest value, so each posting still lands exactly once.
5. **Template keys removed in 3.x:**
   - `fx_revaluation.sql`: `next_ds` and `yesterday_ds` are replaced with `data_interval_end | ds` and `macros.ds_add(ds, -1)`, and `conf` is passed back in, so `[ledger] base_currency` still works.
   - `close_report_weekly`: `prev_ds` is now calculated as the previous week's start (minus 7 days).

Ruff also moved the imports to `airflow.sdk` and the standard providers package. `requirements.txt` now pins `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.

## Verification

- **Checks:** the migration checker reports 0 errors and `ruff --select AIR` passes on `dags/` and `plugins/`.
- **Schedule preview:** for all 6 DAGs, the next 5 runs' fire times, logical dates, data intervals and catchup settings are the same as on 2.11.
- **Replay:** run in the plan's order, so the reports read the close outputs:
  - `gl_postings_hourly`: 36 runs
  - `ledger_housekeeping`: 3 runs
  - `daily_close`: 7 runs, then manual triggers at Mon 03-09 08:15 and Wed 03-11 09:30 UTC
  - `fx_revaluation_daily`: 9 runs
  - `close_report_weekly`: 3 runs
  - `vendor_payments_weekday`: 8 runs, crossing the US clock change on 03-08

  Result: 0 run differences and 0 output differences across 89 files. The Monday trigger re-closed Friday 03-06 with `"started_by": "operator"`, matching 2.11.

## Not covered

- **Manual triggers of the other five DAGs.** They would fail on 3.x with no date, but the runbook doesn't trigger them by hand, so I left them alone. If on-call ever does, they need the same fallback as `daily_close`.
- **Production-only settings.** The replay checks run outputs, not a live scheduler. Make sure production keeps `plugins_folder` set (the timetable and `macros.ledger.*` depend on it) and `AIRFLOW__LEDGER__BASE_CURRENCY=USD`.
- **Tests.** The project has no test suite, so there was nothing to run.