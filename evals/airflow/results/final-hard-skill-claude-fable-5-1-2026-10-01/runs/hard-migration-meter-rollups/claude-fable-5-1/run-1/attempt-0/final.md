The migration is complete and verified. Nothing was committed; the changes are in the working tree on `main`.

**Versions**: `apache-airflow` 2.11.2 to 3.3.2, plus `apache-airflow-providers-standard` 1.19.0 for the Bash and Python operators. No 2.x interpreter exists on this machine, so the BEFORE side ran on 3.3 with the 2.x scheduler defaults. The 2.11 deployment used the stock scheduler defaults, so every schedule kept the 2.x interval semantics.

**Per-DAG decisions**
- **readings_<region>_hourly**: `@hourly` became `CronDataIntervalTimetable`, so each run still lands the hour that just ended. The operator in `plugins/meter_lib/operators.py` keys outlet events by the Asset object; the URI string raised `TypeError` on 3.3.
- **usage_rollup**: `Dataset` became `airflow.sdk.Asset`, and the task reads `triggering_asset_events` keyed by asset. Asset-triggered runs have no data interval on 3.x, so the window is rebuilt as earliest source-run start to latest source-run end, which is exactly what 2.x put in the interval.
- **tariffs_daily**: interval timetable, plus an explicit `catchup=True` because the missing argument meant True on 2.11 and False on 3.x. The script now computes the day as `ds` on scheduled runs and the trigger date on manual runs, with the next day via `macros.ds_add`.
- **billing_daily**: interval timetable. A plain `airflow dags trigger` has no interval on 3.x, so the latest closed day comes from the core timetable's `infer_manual_data_interval`, the same value 2.11 used. The `conf` object was restored to the template context through `user_defined_macros`; the `macros.meter.*` plugin macros still work unchanged.
- **meter_registry_daily**: interval timetable; `execution_date` became `logical_date` with a `run_after` fallback; `provide_context` removed; `Variable.get` uses `default=`.

**Verified**
- Checker: 0 import errors, 0 error findings on `dags/` and `plugins/`; ruff AIR clean (one `AIR003` false positive marked with noqa).
- Next-run preview AFTER equals BEFORE for all 6 DAGs over 5 runs each.
- Replay of 17 runs (3 scheduled per DAG from 2026-03-04 plus both runbook triggers at 2026-03-05 09:15Z) succeeded on the migrated copy. All 19 output files matched a byte-for-byte, independently written 2.x emulation. Every untouched-copy run failed on 3.3 with the expected removed-API errors (string asset key, `execution_date`, `tomorrow_ds`), so there is no executed 2.11 baseline, only the emulated one.
- Runbook triggers run alone on a clean copy: `tariffs_daily` wrote 03-05 and 03-06; `billing_daily` wrote `2026-03-04.csv` and `INV-20260304.csv`, identical to the scheduled file.
- `usage_rollup` callable called with 3.3-style asset events for three hourly runs per region produced `usage_20260304T00_20260304T03` with the expected CSV and manifest row counts.

**Not verified**
- `usage_rollup` was not run through a real scheduler-created asset-triggered run (the replay tooling cannot create asset events), only through the callable with synthetic events.
- `tariffs_daily` with `catchup=True` will create roughly 212 backfill runs when first unpaused on the new cluster, exactly as 2.11 would have. Pause or set a later start date before cutover if that backfill is unwanted.
- The project has no test suite, so none was run or added.