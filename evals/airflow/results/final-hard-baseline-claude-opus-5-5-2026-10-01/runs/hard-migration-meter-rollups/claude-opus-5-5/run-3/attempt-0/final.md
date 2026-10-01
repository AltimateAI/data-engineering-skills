The project is migrated to Airflow 3.3.2. On the same scenario, it produces exactly the same files as the original code does on 2.11. Nothing is committed; the changes are in the working tree.

**How I checked it:** I ran an identical scenario through both local venvs: the original code on 2.11 and the migrated code on 3.3.2. It covered 69 runs:
- **Scheduled runs:** `tariffs_daily` catching up, 27 hours of readings per region, `billing_daily` and the registry export.
- **Batched rollups:** five `usage_rollup` runs, with uneven batches and a late re-landing.
- **Runbook triggers:** both manual triggers with no logical date, including a re-bill just before 02:30, plus a manual registry run.

Every lake, rollup, manifest, billing, registry and dropbox file is byte-identical. The next-run schedule for each DAG also matches. This used Airflow's local test runner with a patched run creator, not a live scheduler, so scheduler-side event batching wasn't exercised.

**What would have changed output on 3.3, and the fix for each:**
- **Cron schedules:** 3.3 treats a cron string as a trigger time with no data interval. Readings would have landed empty files and billing would have billed today instead of yesterday. Every DAG now sets `CronDataIntervalTimetable(..., timezone="UTC")` explicitly.
- **`tariffs_daily` catchup:** it relied on the old default of catching up missed runs, and 3.3 turns that off. It now has `catchup=True`.
- **Runbook triggers:** `airflow dags trigger` (and the REST call with no logical date) creates runs without `ds` or a data interval. Asset-triggered rollup runs have neither either. The new `plugins/meter_lib/runs.py` recreates the 2.11 values, so `billing_daily` still re-bills the latest closed day and `tariffs_daily` still pulls today and tomorrow.
- **Manually triggered readings:** a rollup fed by a manual readings run would have crashed. The rollup now works out that run's hour from the shared readings schedule.
- **Removed template variables:** `conf` and `tomorrow_ds` no longer exist in templates. The dropbox path now comes from a new `macros.meter.invoice_dropbox()`, which reads `[metering] invoice_dropbox` from either `airflow.cfg` or `AIRFLOW__METERING__INVOICE_DROPBOX`; I checked both. Tomorrow's date is computed with `macros.ds_add(ds, 1)`.
- **Renamed APIs:** imports now come from `airflow.sdk` and the standard provider, and datasets are now assets. I removed `provide_context`, renamed `default_var=` to `default=`, and replaced `execution_date` with the logical date. Asset events are now looked up by asset rather than by URI.

**Decision for you — required cutover step:** the 3.3 database upgrade resets the stored trigger time of old `usage_rollup` runs to the end of their data window. Airflow 3 uses that time to decide which new events the next rollup collects. In an upgraded copy of the 2.11 test database, the values came out as 01:00 instead of 01:05, and so on. Left alone, the first rollup after cutover would pick up events the last 2.11 rollup already used. It would get a wider span, a different filename and doubled `rows_delivered`. I've added `ops/airflow3_cutover.sql`, and on that upgraded copy it restores the correct values. Run it once after `airflow db migrate` and before starting the 3.3 scheduler. The README now says so too, and I haven't run it against production.

Two smaller notes:
- `requirements.txt` now pins `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.
- I set `catchup=True` on `tariffs_daily` because 2.11 caught up by default. If production overrides `catchup_by_default=False`, change it to `False`.