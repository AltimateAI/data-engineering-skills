The project is migrated to Airflow 3.3.2, and the run dates match 2.11 for all six DAGs. I could not fully prove identical output files, because there is no 2.11 environment here. Nothing is committed.

**What changed**
- **Schedules:** every time-based DAG now uses an explicit interval timetable, so `ds` and the data intervals mean what they did on 2.11. A bare cron string or `timedelta` would have shifted every output by one period on 3.x. `vendor_payments_weekday` keeps its New York timezone.
- **`catchup`:** all values were already explicit, so I copied them as they were.
- **Removed template keys:**
  - `fx_revaluation.sql` no longer uses `next_ds` and `yesterday_ds`.
  - `conf` is registered as a DAG macro so the `[ledger] base_currency` lookup still works.
  - `close_report_weekly` works out `ds` and `prev_ds` from the previous-week interval.
- **`gl_postings_hourly`:** it reads its cursor from earlier runs with `map_indexes=-1`. Without that, from the third run on 3.x it would get a list of all earlier cursors and re-extract postings.
- **README runbook (`airflow dags trigger daily_close`):** on 3.x a manual run has no data interval, so a new `run_interval` helper in `workdays.py` fills it in. It re-closes the latest business day that has ended, as on 2.11.
- **Audit record:** the operator in `operators.py` used `external_trigger`, which no longer exists on 3.x. It now checks `run_type == "manual"`, so manual runs still write `"started_by": "operator"`.
- **Imports and pins:** imports moved to `airflow.sdk` and the standard provider. `requirements.txt` pins `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.
- **Plugin:** the `macros.ledger.fiscal_period` macro and the `WorkdayTimetable` registration are unchanged and still work.

**What I checked**
- The project checker exits 0 with no import errors, and `ruff --select AIR` is clean on `dags/` and `plugins/`.
- Run dates, data intervals and `catchup` match the 2.x defaults for all six DAGs.
- I replayed 3–4 scheduled runs per DAG plus a manual `daily_close` run (trigger at 2026-03-04 09:15 UTC), and all of the migrated runs succeeded.
- The manual run re-closed Tuesday 03-03 and wrote `started_by: operator`. The scheduled runs wrote `scheduler`.
- The 2.x baseline here is 3.x with the 2.x scheduler defaults switched back on, because there is no 2.11 environment. Its `daily_close` and `fx_revaluation_daily` runs failed on the removed keys, and the later `gl_postings_hourly` runs failed on the XCom list. Those have no baseline, so I checked their outputs by reading them against the 2.x behaviour, not by diffing.
- The replay's six reported differences are all artifacts of those baseline failures. Weekly report `prev_ds` showed `None`, and housekeeping batch counts were lower because the baseline's hourly runs had failed. The migrated values are the 2.11 ones.

**Before cutover**
- Run the same replay plan on a real 2.11 environment for a true before/after file diff. A Monday manual re-close, which should pick the previous Friday, was not replayed. It uses the same `infer_manual_data_interval` code as the 2.x timetable.
- The checker still shows manual-run warnings on the other DAGs. The runbook only triggers `daily_close` manually, so I left them.
- The repo has no tests, so none were added or run.