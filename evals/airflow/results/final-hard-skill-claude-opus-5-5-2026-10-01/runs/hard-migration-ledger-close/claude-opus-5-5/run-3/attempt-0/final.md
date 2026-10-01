The project is migrated to Airflow 3.3.2. I replayed it on the real 2.11.2 environment and on 3.3.2, and every scheduled run and the runbook re-close wrote byte-identical files on both, `.meta.json` audit records included. Nothing is committed yet; the changes are in the working tree.

## Changes that keep the outputs the same
None of these problems raises an error when the DAGs load. Each one either fails only when the task runs or quietly writes different data.

| Where | Problem on 3.x | Fix |
|---|---|---|
| All 5 cron/`timedelta` DAGs | On 3.x a bare cron string or `timedelta` runs each period at its start instead of after it ends, so every `ds`/output date would move one period later | Explicit `CronDataIntervalTimetable` / `DeltaDataIntervalTimetable` with the same cron and timezone (New York for `vendor_payments`). Existing `catchup` values unchanged |
| `sql/fx_revaluation.sql` | `next_ds`, `yesterday_ds` and `conf` no longer exist in templates, so the task would fail | `data_interval_end \| ds`, `macros.ds_add(ds, -1)`, and `conf` passed in via `user_defined_macros` (`[ledger] base_currency` still works) |
| `close_report_weekly` | `prev_ds` parameter would silently be `None`, so it would never compare against the previous week | Computed as the interval start minus one week |
| `gl_postings_hourly` | From the 3rd run on, the XCom cursor comes back as a list of all past values, which breaks "each posting lands exactly once" | `map_indexes=-1` (returns the latest value) |
| `DuckDbSqlOperator` audit record | `dag_run.external_trigger` is gone in 3.x, so writing the record would fail | `run_type == "manual"` → `"operator"`, otherwise `"scheduler"` |
| `daily_close` manual re-close | `airflow dags trigger daily_close` gets no logical date or data interval on 3.x, so the target path and SQL would fail | New `close_interval(dag_run)` helper in `plugins/ledger_lib/workdays.py`: scheduled runs use their own interval, a manual trigger uses the timetable's existing rule (latest workday that has ended; Monday morning → Friday). The runbook command stays the same |

I also moved imports to `airflow.sdk` / `airflow.providers.standard`, and pinned `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0` in `requirements.txt`. The plugin's timetable and `macros.ledger.fiscal_period` registration are unchanged.

## How it was checked
- **Static checks:** the migration checker reports 0 import errors and 0 errors on `dags/` and `plugins/`, and `ruff --select AIR` passes.
- **Schedule preview:** the next 5 runs of each of the 6 DAGs have the same fire times, logical dates and data intervals on 3.3 as on 2.11.
- **Replay:** 33 runs, each with one shared metadata database per side:
  - `gl_postings_hourly`: 8 runs.
  - `ledger_housekeeping`: 3 runs.
  - `daily_close`: 8 scheduled runs plus 2 runbook triggers, one on Monday 03-09 08:30 (re-closed Friday) and one on 03-11 14:00 (re-closed 03-10).
  - `close_report_weekly`: 3 runs.
  - `fx_revaluation_daily`: 4 runs.
  - `vendor_payments_weekday`: 5 runs, including the Friday→Monday weekend window.

  All 33 runs succeeded on both sides, and a recursive `diff` of the two output trees was empty.

## Not covered
- The repo has no test suite, so there were no project tests to run.
- `uv` and the backfill CLI were not exercised. For the record, 3.x backfills are labelled `"scheduler"` in the audit record, the same as on 2.x.
- The checker warns that the other DAGs would fail on a manual trigger on 3.x. The runbook only triggers `daily_close` by hand, so I left them alone. Tell me if on-call ever triggers the others and I'll add the same fallback.

The deployment needs the same settings as before: `plugins_folder=plugins/` on the DAG processor and workers, and `AIRFLOW__LEDGER__BASE_CURRENCY=USD`.