Both DAGs now run on Airflow 3.3.2, and the events still load exactly once. The changes are uncommitted in the working tree, and I haven't committed anything.

**What I checked**
- **Import and schedule check:** the checker reports 0 errors. The 2.x versus 3.x schedule preview matches for both DAGs, with the same run times, logical dates and data intervals.
- **Hourly loads:** `airflow dags test` on the 19:00, 20:00 and 21:00 ticks loaded 63 events with 0 duplicates, which matches the 63 events in the source file up to 21:00.
- **Rerun:** re-running the 20:00 tick wrote the identical batch, so a retry doesn't double-load.
- **Scorecard:** `carrier_scorecard` ran and wrote `carrier_scorecard.csv` and `_READY` (`carriers=4 shipments=43`).

**Changes**
- **`ingest_shipments`, schedule:** `"@hourly"` becomes `CronDataIntervalTimetable("0 * * * *")`. A bare cron string is a different schedule on 3.x, so this keeps the 2.x periods. `catchup=False` is unchanged.
- **`ingest_shipments`, watermark:** the last-loaded timestamp used to be read from the metadata DB, which tasks can't query on 3.x. Each batch now writes a small `batch_<ts>.watermark` file beside it, and the next run reads the latest earlier one. The scorecard's `batch_*.csv` glob ignores these files. The watermark rule is unchanged: it still loads events with `updated_at` strictly after it.
- **`carrier_scorecard`:** the `_READY` template now reads its values from the scorecard task by name. Without that, 3.x would have written empty values.
- **Imports and housekeeping:**
  - Imports moved to `airflow.sdk` and the standard provider, and `Dataset` became `Asset`.
  - `requirements.txt` is pinned to `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.
  - The README now says "asset".

**For Monday**
- **Watermark files:** production needs the `output/warehouse/shipments/` directory to persist between runs, as the batches already require. The first 3.x run has no watermark file and would reload everything after `start_date`. If production already has batches, seed the latest `.watermark` file with the high-water mark from the last 2.x load, or the first run will load duplicates.
- **Not tested:** I never ran this on a real scheduler. I also didn't test the scorecard being triggered by the ingest asset update; I ran it directly instead. No 2.x environment was available, so the baseline schedule preview came from 3.3 with the 2.x defaults switched on.
- **Ruff AIR001:** it flags the `build` variable name in `carrier_scorecard`. I left it, since renaming it would clash with the function of the same name.