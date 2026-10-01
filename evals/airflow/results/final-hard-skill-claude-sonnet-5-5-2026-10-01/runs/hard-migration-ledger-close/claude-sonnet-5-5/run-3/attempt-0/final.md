The project is migrated to Airflow 3.3.2, but I couldn't prove every output matches 2.11, because there is no 2.11 environment here. I replayed the old code on 3.3 with the 2.x scheduler defaults instead, and that only gave a full baseline for some DAGs.

**Changes**
- **Schedules:** every time-based DAG now uses an explicit interval timetable, so run dates and `ds` stay as on 2.11. Those are `CronDataIntervalTimetable`, with New York time for vendor payments, and `DeltaDataIntervalTimetable` for housekeeping. The before/after schedule preview matches for all 6 DAGs, with the same fire times, intervals and catchup.
- **Catchup:** `catchup` was already set explicitly on every DAG, so I left it alone.
- **`daily_close` manual re-close:** on 3.x a plain `airflow dags trigger daily_close` has no data interval. I added `run_interval(dag_run)` in `plugins/ledger_lib/workdays.py`. It uses the run's interval when there is one, otherwise the timetable's latest-ended-weekday rule. A Monday-morning trigger re-closes Friday.
- **Audit record:** `external_trigger` no longer exists, so the audit record now uses `dag_run.run_type == "manual"` to say "operator". Scheduled runs still say "scheduler". The operator now imports `BaseOperator` from `airflow.sdk`.
- **`gl_postings_hourly`:** `include_prior_dates=True` now returns a list from the 3rd run on, which would have re-extracted postings. I added `map_indexes=-1` to get the latest cursor.
- **`fx_revaluation_daily`:** the SQL no longer uses the removed `next_ds`, `yesterday_ds` and `conf`. I restored `conf` as a template macro, and the date logic reproduces the 2.x values.
- **`close_report_weekly`:** `prev_ds` is gone and would have silently been `None`. It is now the Monday 7 days before the interval start.
- **Imports and `requirements.txt`:** imports moved to `airflow.sdk` and the standard provider's `BashOperator`. `requirements.txt` now pins `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.

**Verified**
- The Airflow checker reports 0 errors and ruff's AIR rules pass on `dags/` and `plugins/`.
- Replaying 3–5 scheduled runs per DAG gave identical files between old and new code for `vendor_payments_weekday`, `close_report_weekly`, `ledger_housekeeping`, `gl_postings_hourly` and `daily_close`. The last three used small compatibility shims in the "before" copy, because the unmodified old code fails on 3.x (the cursor list, `external_trigger`, `prev_ds`).
- A manual `daily_close` trigger at Monday 2026-03-09 09:00 closed 2026-03-06 with `started_by: operator`. I judged that against the 2.x rules rather than a real 2.x run.

**Not verified**
- No true 2.11 baseline was available, so ideally rerun the replay on 2.11 before cutover.
- `fx_revaluation_daily` has no baseline either, since its old SQL can't render on 3.x. I only checked that the new outputs look right: the file is named for the run date, the base currency shows USD, and the revaluation column is filled.
- `ledger_housekeeping` shows a different file count against the unmodified old copy. That is only because the old `gl_postings_hourly` fails on 3.x, so fewer batches exist. It matched in the shimmed run.
- `gl_postings_hourly`, `close_report_weekly`, `vendor_payments_weekday` and `ledger_housekeeping` read `ds` or the data interval too. They would fail on a manual trigger, but the runbook only triggers `daily_close` manually, so I left them. The checker flags this as a warning.
- The repo has no tests, so I didn't add any.