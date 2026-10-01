Migration complete and verified: the migrated project on Airflow 3.3.2 writes byte-identical outputs to the untouched project on Airflow 2.11.2 across 26 replayed runs, including both manual re-closes from the runbook.

**What changed, per DAG**

- **All five time-scheduled DAGs** now use explicit interval timetables instead of bare cron strings or a `timedelta`. On 3.x a bare string is a trigger timetable, so every run date, `ds` and data interval would have shifted one period later. Explicit `catchup` values were already present and were kept.
- **daily_close** keeps the custom `WorkdayTimetable` and the plugin macro `macros.ledger.fiscal_period`. The business day now comes from one helper, `close_interval`, used by the SQL template, the output path and `roll_balances`. On a 3.x manual trigger the data interval is empty, so the helper infers it from the trigger time the same way 2.11 did (Monday morning re-closes Friday).
- **fx_revaluation_daily**: the SQL template used `next_ds`, `yesterday_ds` and `conf`, all removed from the 3.x context. They are rebuilt in the template, and `conf` is passed in via `user_defined_macros` from `airflow.sdk`.
- **close_report_weekly**: the `prev_ds` task parameter would have silently been `None`. It is now the previous weekly tick, or the run's own date on a manual run, as on 2.11.
- **gl_postings_hourly**: the cross-run XCom cursor gets `map_indexes=-1`. Without it, 3.x returns a list of every earlier value from the third run on, and postings would reload.
- **vendor_payments_weekday** keeps the New York timezone through the timetable object. **ledger_housekeeping** uses a delta interval timetable so the file stamp stays the window start.
- **Plugin operator**: `dag_run.external_trigger` no longer exists on 3.x, so the audit record's `started_by` now comes from the run type. The timetable and macro registration in the plugin are unchanged and still work on 3.3.
- New shared module `plugins/ledger_lib/runs.py` holds the manual-run helpers. Requirements pinned to Airflow 3.3.2 plus the standard provider. README notes the 3.3 deployment and that `plugins_folder` must be set on workers too.

**Verified**

- Migration checker: 0 import errors, 0 errors. Ruff AIR rules: clean on `dags/` and `plugins/`.
- Scheduled-run preview: all 6 DAGs match the preview taken with the real 2.11 interpreter (5 runs each).
- Full replay against one metadata DB per side, 2.11 before vs 3.3 after: 6 hourly extracts, 5 daily closes plus manual re-closes on Wed 03-04 and Mon 03-09, 3 FX, 3 weekly reports, 4 payment runs, 3 housekeeping. Result: identical runs and identical files. The re-closed days 03-03 and 03-06 carry `started_by: operator`; FX output shows USD from the `AIRFLOW__LEDGER__BASE_CURRENCY` setting.

**Not verified or left as is**

- The repo has no test suite, so nothing was run under pytest. Nothing was committed.
- The `pendulum.now()` in the workday timetable's no-catchup branch is pre-existing 2.x behaviour and unused since `daily_close` has `catchup=True`. I left it unchanged.
- Manual triggers of DAGs other than `daily_close` are not in the runbook. They were made to work on 3.x with 2.11 semantics but were not replayed.