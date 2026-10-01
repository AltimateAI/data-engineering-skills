The project now imports and runs on Airflow 3.3.2, and every scheduled and manual run I could replay writes the files I expect. I could not prove the match against real 2.11 output, and I could not replay the asset-triggered rollup at all.

**What I checked**
- The airflow_check script reports 0 import errors and 0 errors. Ruff's AIR rules are clean.
- The previewed run dates, intervals and `catchup` values for every time-scheduled DAG are identical to the 2.x values.
- I replayed 3 scheduled runs per DAG plus manual triggers on 3.3, and every migrated run succeeded.
- There is no 2.x environment here. The replay's baseline was therefore the old code run on 3.3, which fails on the removed template keys, so there were no baseline files to diff against. I checked the manual-run results by hand against the 2.x behaviour:
  - Manual `billing_daily` at 2026-03-06 09:15 bills 03-05, and at 01:15 it bills 03-04. That is the latest closed day, as the README says.
  - Manual `tariffs_daily` at 03-06 writes 03-06 and 03-07, so today plus tomorrow.
  - Manual `meter_registry_daily` writes its file for the trigger date.
- `usage_rollup` could not be replayed, because the replay can't generate asset events. Its window logic comes from the reference notes and has not been run.
- The repo has no tests, so there was nothing to run. I didn't add any.

**Changes that keep behaviour identical**
- **Schedules:** every time-based DAG (hourly regions, `tariffs_daily`, `billing_daily`, `meter_registry_daily`) now uses an explicit cron-interval schedule. A bare cron string means something different on 3, and the run dates would have shifted by a period.
- **`tariffs_daily` catchup:** it had no `catchup` setting, which meant catching up on 2.x. I set `catchup=True` explicitly. On unpause it will create about 212 backfill runs, as it would have on 2.11.
- **`sync_tariffs.sh`:** `tomorrow_ds` no longer exists. The script now takes the day from `ds`, or from the trigger date on a manual run, and adds one day.
- **`billing_daily` manual runs:** a manual run has no data interval on 3, so the task rebuilds the latest closed interval from the trigger time.
- **`publish_invoices.sh`:** `conf` is gone from the template context, so I added it back through `user_defined_macros`.
- **`meter_registry_daily`:** it now uses the logical date, or the trigger time for a manual run, for both the `as_of` field and the file name. `Variable.get` uses `default=`.
- **`usage_rollup` and assets:**
  - Datasets became Assets, and the plugin operator now indexes `outlet_events` by the asset rather than by its URI.
  - The rollup rebuilds its window from the source runs' intervals, as 2.x did, because asset-triggered runs have no data interval on 3.
- **`requirements.txt`:** it pins `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.

I also added a `# noqa: AIR003` on the `Variable.get` line in `meter_registry.py`, because ruff flags it even though it runs at task time.

**Before cutover**
- Set `AIRFLOW__METERING__INVOICE_DROPBOX` on the 3.x deployment. Without it `publish_invoices` fails.
- Point both the DAG processor and the workers at the same `plugins/` folder.
- Run one `usage_rollup` on a staging cluster and compare its CSV and manifest with 2.11 before trusting it.

Nothing is committed. The changes are in the working tree.