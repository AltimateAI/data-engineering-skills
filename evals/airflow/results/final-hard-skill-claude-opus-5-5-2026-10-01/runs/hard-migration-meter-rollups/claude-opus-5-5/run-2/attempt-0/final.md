The project now runs on Airflow 3.3.2 and produces the same files as on 2.11.2, byte for byte, in every run I replayed. I tested against a real 2.11.2 environment (the one at `~/.cache/des-evals/agent-airflow-2.11`), not a simulation. Nothing is committed yet.

## Verification

| Check | Result |
|---|---|
| Static checker on `dags/` and `plugins/` | 0 import errors, 0 errors |
| Schedule preview, 2.11 vs 3.3 (5 runs per DAG: run dates, intervals, catchup) | Match for all 6 DAGs |
| Replay of the same runs on 2.11 and 3.3, then diff of `output/` | **Identical** across 22 runs (below) |
| `usage_rollup` asset-triggered runs, plus `tariffs_daily` and `billing_daily` built on them | **Identical** (below) |

**The 22-run replay** covered:
- 3 or 4 consecutive scheduled runs of each time-based DAG.
- `airflow dags trigger tariffs_daily` from the runbook.
- `airflow dags trigger billing_daily` from the runbook, at 01:15 and at 09:15, to check that "latest closed billing day" is right before and after the 02:30 close.
- One manual run of `meter_registry_daily`.

**The `usage_rollup` test:** the replay tool can't produce asset events, so I wrote a small test script. The regional DAGs land readings, then each version's own scheduler code creates the triggered rollup runs. It ran 3 batched rollups, then `tariffs_daily` and `billing_daily` on top. The rollup CSVs and `.json` manifests (including the row counts per region) were identical, and so were the billing CSV and the `INV-20260304.csv` dropbox file.

## What changed and why

- **All time-scheduled DAGs** now use `CronDataIntervalTimetable` with the same cron. On Airflow 3 a bare cron string means the run's date is the day it fires, which would shift every billing day and file name forward by one period. This keeps the 2.x dates.
- **`tariffs_daily`** now sets `catchup=True` explicitly. It had no `catchup` setting, which meant True on 2.x but means False on 3.x.
- **`sync_tariffs.sh`**: `tomorrow_ds` no longer exists, so the template now adds one day to `ds`. Manual triggers have no date on Airflow 3, so the template uses the trigger day instead. The runbook's "today and tomorrow" still holds.
- **`billing_daily`**:
  - Manual triggers have no billing interval on Airflow 3, so `bill` works out the latest closed billing day the way 2.x did.
  - `conf` is no longer available in templates by default, so I passed it back in explicitly. Without that, `publish_invoices.sh` would fail to find the `[metering] invoice_dropbox` setting.
  - The `macros.meter.invoice_batch` plugin macro is unchanged and still works.
- **`usage_rollup`**: Airflow 3 gives asset-triggered runs no time window. The task now rebuilds it from the regional runs that triggered it: earliest start to latest end, as on 2.x. Row counts are looked up by asset object rather than by URI string.
- **`meter_registry_daily`**: `execution_date` is now `logical_date`. A manual run uses the trigger time, as on 2.x. I renamed the callable to `write_registry_snapshot`; the task id is unchanged.
- **Plugins**: `Dataset` became `Asset` (same URIs), and `CsvSliceOperator` now uses the `airflow.sdk` `BaseOperator` and records its events by asset object.
- **Imports** moved to `airflow.sdk` and `airflow.providers.standard`.
- **`requirements.txt`**: `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.

Task ids, output paths, file names and formats are all unchanged.

## Before you cut over

- **Production setup**: the 3.x deployment needs the same `plugins_folder` on the DAG processor and on the workers, and `AIRFLOW__METERING__INVOICE_DROPBOX` must still be set.
- **Catchup on `tariffs_daily`**: this preserves today's behaviour, but if the 3.x database is fresh, unpausing it will backfill about 212 days, from 2026-03-03 to now. To avoid that, carry the run history over or unpause it deliberately.
- **Not tested**:
  - The `usage_rollup` test ran in-process, not through a live scheduler.
  - Manual triggers of the hourly regional DAGs and of `usage_rollup` weren't tested. The runbook doesn't use them.
- **Linter warning left in place**: ruff flags `Variable.get()` in `meter_registry.py` as running "outside of a task". It's a false positive: the call is inside the `PythonOperator` callable.
- **No test suite**: the repo has none, so there were no project tests to run.