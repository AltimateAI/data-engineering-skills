The project is migrated to Airflow 3.3.2. Every scheduled run and the `daily_close` manual re-close wrote byte-identical files to 2.11, `.meta.json` audit records included, in a replay I ran on both venvs. I haven't committed anything.

## What I checked

- **Replay on both versions:** I ran the original code on the 2.11 venv and the migrated code on 3.3, each in its own copy with a fresh database. Both replayed the same 438 runs: every scheduled run of all six DAGs from 1–16 March 2026 (this crosses the US daylight-saving change on 8 March), plus three runbook re-closes. Every run changed exactly the same files with the same contents, and the final `output/` trees match.
- **Real CLI trigger:** on 3.3, `airflow dags trigger daily_close` (run today, a Thursday) re-closed Wednesday 2026-09-30, and its audit record says `"started_by": "operator"`. I ran its two tasks with `airflow tasks test`, not a running scheduler.
- **Parsing:** all DAGs parse with no import errors, and the plugin still registers the timetable and the `macros.ledger` macro.

## Changes that kept outputs the same
A mechanical upgrade would have changed the outputs in these places:

1. **Schedules:** in 3.x, a plain cron or timedelta schedule now starts runs at a single point in time instead of covering an interval. That changes `ds`, `ts` and every file name, and Monday's vendor payment run would no longer cover the weekend. Each DAG now names the 2.x-style interval schedule explicitly (`CronDataIntervalTimetable` / `DeltaDataIntervalTimetable`) rather than relying on a config default.
2. **Removed template variables:**
   - `next_ds` became `data_interval_end | ds` and `yesterday_ds` became `macros.ds_add(ds, -1)`, both in `fx_revaluation.sql`.
   - `prev_ds` in the weekly report is now computed as one week before the run.
   - `conf` is no longer available in templates, so `fx_revaluation_daily` passes it in itself.
3. **Audit record:** `dag_run.external_trigger` no longer exists. `started_by` is now based on the run type: "manual" and "operator_triggered" count as "operator", as they did on 2.11.
4. **Runbook re-close:** on 3.x, triggering without a logical date creates a run with no date range at all. A new helper, `run_data_interval`, falls back to the timetable's rule for manual runs ("latest business day that has ended"), as 2.11 did.
5. **Hourly extract:** in 3.3, `xcom_pull(..., include_prior_dates=True)` returns a list of every earlier cursor instead of the latest one. The extract crashed on its second run in my first replay, and I fixed it by adding `map_indexes=-1`.

Also: imports moved to `airflow.sdk` and the standard provider's `BashOperator`, and `requirements.txt` now pins `apache-airflow==3.3.2` plus `apache-airflow-providers-standard`.

## Not covered
- **Manual triggers of other DAGs:** the runbook only covers `daily_close`, so that is all I made work for manual runs. A plain `airflow dags trigger` of any other DAG on 3.3 has no logical date, so it will fail or behave differently than on 2.11. If on-call ever does that, I can extend the same fallback.
- **The cutover itself:** I didn't simulate migrating the production 2.11 database. Because the schedule types are unchanged, the 3.3 scheduler should carry on from the last 2.11 run without skipping or repeating one.