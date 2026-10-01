The project now runs on Airflow 3.3.2. I ran a real 3.3 scheduler, DAG processor and API server against a scratch copy of the project, and every scheduled, asset-triggered and runbook manual run wrote the same files 2.11 would. Nothing is committed yet.

**What would have silently changed the files on 3.3, and how I kept the 2.11 behaviour:**
- **Cron schedules:** 3.3 runs cron schedules with a new default timetable (`CronTriggerTimetable`) where a run's start and end are both just the run time. Billing, tariffs, readings and registry would all have processed the wrong day or hour. All four now use `CronDataIntervalTimetable` explicitly, which is how 2.11 behaved.
- **Runbook manual runs:** in 3.3, a plain `airflow dags trigger` creates a run with no logical date and no data interval. The new `plugins/meter_lib/runs.py` rebuilds the dates from the trigger time the way 2.11 did:
  - `billing_daily` bills the latest closed billing day.
  - `tariffs_daily` syncs today and tomorrow.
  - `meter_registry_daily` uses the trigger time for its date and `as_of`.
- **Asset-triggered rollups:** in 3.3 these runs also have no data interval. `usage_rollup` now rebuilds 2.11's span: from the earliest start to the latest end of the readings runs that triggered it. I also set `catchup=True` on it. The only thing that flag changes in 3.3 is how far back the first rollup run reads events, and `True` matches 2.11.
- **Catchup default:** `catchup` now defaults to False, so `tariffs_daily` gets an explicit `catchup=True` to keep its 2.11 default.
- **Templates:** 3.3 dropped `tomorrow_ds` (used in `sync_tariffs.sh`) and the `conf` template variable (used in `publish_invoices.sh` for the dropbox path). Both are replaced and the scripts behave the same.
- **Asset events:** `outlet_events` and `triggering_asset_events` no longer accept URI strings as keys, so both now use the asset itself. The row counts in the manifest are unchanged.
- **Mechanical renames:** imports now come from `airflow.sdk` and the standard provider, `schedule_interval` became `schedule`, and the old `Variable.get`/`execution_date`/`provide_context` usages are updated. `requirements.txt` pins `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.

**What the end-to-end test showed:**
- **Readings to rollup:** three backfilled hours plus one scheduled hour in each region triggered a single rollup, `usage_20260304T00_20261001T12`. Its manifest had the correct row counts per event.
- **Tariffs:** catch-up runs synced the previous day plus the next one. A manual trigger synced 10-01 and 10-02. The manual test used a scratch-only edit with catchup turned off.
- **Billing:** the scheduled run billed 09-30 and published `INV-20260930.csv`. A manual trigger also billed 09-30. The 09-30 tariffs and rollup were made-up data I added in the scratch copy, because the sample data only covers March.
- **Registry:** the scheduled run wrote `2026-09-30.json` with `as_of` 2026-09-30T00:00:00+00:00. A manual run used the trigger time with no microseconds, as 2.11 did.

**Before cutover:**
1. **Ops scripts using the REST API:** 3.3 only serves `/api/v2`, and the request body has to include `"logical_date": null`. I've added this to the README runbook; the scripts themselves aren't in this repo, so they need updating separately.
2. **Manual runs of `readings_<region>_hourly` (not in the runbook):** these now fail when the task starts. On 2.11 they would have landed the last full hour. Fixing this would mean changing the operator, so I've left it. Use `airflow backfill create` with explicit dates instead.
3. **Production `catchup_by_default`:** if production ever set this to False, remove the explicit `catchup=True` I added to `tariffs_daily`.
4. **Run ids and the database:** scheduled run ids now come from the run time rather than the logical date (`scheduled__2026-10-01T02:30…`). File names are unaffected. The 3.x database migration converts existing dataset-triggered runs, so rollup batching continues correctly across the cutover.