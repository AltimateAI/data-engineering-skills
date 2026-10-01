The migration is done and all six DAGs parse cleanly on 3.3.2. I couldn't fully test scheduled runs, though. A stray process on port 8080 returned 501s and killed my local scheduler. I checked the DAGs one at a time with `airflow dags test` instead.

**What I changed**
- **Schedules:** 3.x makes plain cron strings and timedeltas into "trigger" schedules with no data interval, which would have shifted `ds` and the data intervals. I set the hourly, weekly, FX, vendor-payments and housekeeping schedules explicitly to `CronDataIntervalTimetable` or `DeltaDataIntervalTimetable`. Vendor payments uses the New York timezone, as before.
- **Imports:** DAGs and operators now import from `airflow.sdk`. `BashOperator` comes from the standard provider, and I added `apache-airflow-providers-standard` and `apache-airflow==3.3.2` to `requirements.txt`.
- **Audit record:** `dag_run.external_trigger` no longer exists, so `started_by` is now based on `run_type == manual`. Scheduled runs still write `scheduler`, and manual runs still write `operator`.
- **Removed template variables:**
  - `next_ds` and `yesterday_ds` in `fx_revaluation.sql` are now `macros.ds_add(ds, ±1)`.
  - `prev_ds` in the weekly report is now the week start minus 7 days.
- **`conf` in templates:** it is no longer available, so the FX DAG passes it in through `user_defined_macros`. `conf.get('ledger','base_currency')` still reads `AIRFLOW__LEDGER__BASE_CURRENCY`.
- **No change needed:** the `WorkdayTimetable` and the `macros.ledger.fiscal_period` plugin work as they were.

**What I checked**
- `daily_close` re-close: with the same code the timetable uses for the plain CLI trigger, a trigger on Monday 2026-10-05 gives Friday 2026-10-02. A trigger on Thursday gives Wednesday.
- A manual `daily_close` run writes `net.csv`, `balances.csv` and a `net.meta.json` saying `operator`.
- The FX query renders and writes its CSV and meta file.
- The hourly extract's cursor carries over between runs. The second batch did not repeat the first batch's postings.
- A scheduled run's audit record saying `scheduler` and the weekly report's comparison with the previous week's file were not exercised end to end. The vendor-payments and housekeeping DAGs were not run at all.

**Before cutover**
- Compare real output on a staging scheduler against 2.11 for a few days. That should cover the weekly report's comparison, the vendor-payments Monday weekend window, and the 12-hour housekeeping file names.
- In 2.11, `prev_ds` was the previous scheduled run's date. I used exactly 7 days earlier. These differ only if a weekly run was skipped.

I did not commit anything.