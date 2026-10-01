The project now imports and runs on Airflow 3.3.2. A replay against a real 2.11.2 env produced identical output files for every DAG except `usage_rollup`, which I couldn't replay. I haven't committed anything.

**What I changed**
- **Schedules:** every time-scheduled DAG uses `CronDataIntervalTimetable`, so the 2.x run dates and `ds` values are unchanged:
  - `readings_*_hourly` uses `0 * * * *`.
  - `meter_registry_daily` uses `0 0 * * *`.
  - `tariffs_daily` and `billing_daily` keep their existing crons.
- **`tariffs_daily` catchup:** it had no `catchup`, which meant `True` on 2.x, so I set `catchup=True` explicitly. Once unpaused it will create about 212 backfill runs from its 2026-03-03 start date, as it would on 2.11.
- **`tariffs_daily` template:** `sync_tariffs.sh` no longer uses `tomorrow_ds`. It takes the day from `ds`, or from the trigger time on a manual run, and adds one calendar day.
- **`billing_daily` manual runs:** a manual trigger re-bills the latest closed billing day, using the 2.x manual-interval inference. `conf` is re-exposed to the publish template.
- **`meter_registry_daily`:** it uses `logical_date`, falling back to the trigger time on manual runs. `Variable.get` takes `default=`.
- **`usage_rollup`:** it rebuilds the 2.x window, from the earliest source interval start to the latest end, out of the triggering asset events. It reads `triggering_asset_events` by `Asset` object.
- **Plugins:** `Dataset` became `Asset`, and `CsvSliceOperator` now takes `BaseOperator` from `airflow.sdk` and indexes `outlet_events` by asset object. The `macros.meter.*` plugin is unchanged.
- **`requirements.txt`:** pinned to `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`, with `pendulum` unchanged.

**What I checked**
- The 2.x and 3.x previews give identical run dates, data intervals and catchup for every DAG, and the checker reports 0 errors.
- I replayed three scheduled runs per time-scheduled DAG, plus manual triggers (plain `airflow dags trigger`, no config) of `billing_daily`, `tariffs_daily` and `meter_registry_daily`. All three sides ran on one metadata DB. The output files were identical.
- One mismatch turned out to be a line-ending difference in the working tree. `data/*.csv` is CRLF on disk but LF in git HEAD, so `tariffs_daily` copied `\r` into its output. I replayed from `git archive HEAD` and it matched. Check that `data/` has the same line endings wherever it's deployed.

**What I did not verify**
- **`usage_rollup`:** it is asset-triggered and can't be replayed offline. I checked its logic against the 2.x behaviour but never ran it, so its rollup files and manifests are untested. Please run it once on staging before cutover.
- **Tests:** the repo has no tests, so none were run.
- **Ruff:** it flags `Variable.get` in `meter_registry.py`. That call is inside the task callable, so I believe it's a false positive.