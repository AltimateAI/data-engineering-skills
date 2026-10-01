The project is migrated to Airflow 3.3.2. I ran the same runs on the real Airflow 2.11.2 env (untouched code) and on 3.3.2 (migrated code), and every output file is byte-identical. The changes are in your working tree, not committed.

## What I tested

| Runs | Result |
|---|---|
| `readings_east_hourly` and `readings_west_hourly`: 3 hourly runs each | identical |
| `tariffs_daily`: 3 scheduled runs, plus the runbook trigger (no date, no config) at 03-06 09:15 | identical (03-06 and 03-07 tariffs synced) |
| `meter_registry_daily`: 3 runs, with the `registry_version` Variable set | identical |
| `billing_daily`: 2 scheduled runs, plus the runbook trigger at 01:15 and at 09:15 | identical billing files and `INV-*.csv` dropbox files |
| `usage_rollup`: a real asset-triggered run created by the scheduler from 3 loads (two east hours, one west hour, batched into one run) | identical CSV and manifest (window 00→02, `rows_delivered` east 24 / west 8) |

- **Schedules:** the next 5 run dates, data intervals and catchup settings match 2.11 for every DAG.
- **Billing data:** I put the same two rollup files in both copies first, so billing priced real rows and the "latest rollup wins" rule was exercised.
- **Checks:** the migration checker reports 0 errors. Ruff flags one thing, `Variable.get()` in `meter_registry.py`. It's a false positive: that call already runs inside the task, not at parse time.

## Changes that keep the behaviour the same
Airflow 3 changed several defaults without raising errors, so each one needed a fix:
- **Schedules:** a plain cron string or `@hourly`/`@daily` now means something different on 3.x and would have shifted every output by one period. All four timed DAGs now use `CronDataIntervalTimetable`, which keeps the 2.x dates.
- **`tariffs_daily` catchup:** it never set `catchup`, so on 2.x it caught up by default. The 3.x default is off, so I set `catchup=True` explicitly.
- **Runbook triggers:** on 3.x a plain `airflow dags trigger` run has no date at all.
  - `billing_daily` now works out the latest closed billing day from the trigger time, the same way 2.x did.
  - `sync_tariffs.sh` uses the trigger day and the day after. It used `tomorrow_ds`, which no longer exists.
  - `meter_registry_daily` uses the trigger time if it's run by hand.
- **Dropbox setting:** templates can no longer read `conf` directly. I passed it to `billing_daily` explicitly, so `publish_invoices.sh` still finds `[metering] invoice_dropbox`.
- **`usage_rollup`:** on 3.x an asset-triggered run has no time window. It now rebuilds the 2.x window (earliest to latest hour of the triggering loads) from the asset events. I also renamed the old dataset parameter, changed how events are looked up, and moved Dataset to Asset in `plugins/meter_lib/`.
- **Operator and Variable:** `CsvSliceOperator` now imports from `airflow.sdk`. `Variable.get` now takes `default=` (the old `default_var=` is rejected).
- **Unchanged:** task ids, file names, output paths, formats and the `macros.meter.*` plugin all stay as they were.
- **Packages:** `requirements.txt` now pins `apache-airflow==3.3.2` and adds `apache-airflow-providers-standard==1.19.0`.

## Before cutover
- **One manual case left as it was:** a manual trigger of the hourly `readings_*` DAGs would fail on 3.x, because there is no hour to land. These aren't in the runbook, so I didn't add handling. Tell me if ops ever trigger them by hand and I'll add it.
- **Rollup edge case not tested:** a rollup run triggered by hand (rather than by asset events) should behave like 2.x, writing an empty rollup at the trigger time. I didn't run that case.
- **On the 3.x cluster:** the DAG processor and workers need the same `plugins_folder`, and production still needs `AIRFLOW__METERING__INVOICE_DROPBOX` set.
- **No tests:** the repo has no test suite, so there were no project tests to run.