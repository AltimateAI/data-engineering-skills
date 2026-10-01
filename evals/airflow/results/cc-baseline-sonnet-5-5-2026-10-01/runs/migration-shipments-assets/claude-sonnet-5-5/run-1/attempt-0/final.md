Both DAGs now run on Airflow 3.3.2 in the local venv. I tested with `dag.test()` in a throwaway Airflow home. `_READY` shows `carriers=4 shipments=63`, and the scorecard has the same four carrier rows as the pre-migration code produced. Nothing is committed.

**What changed**
- **Imports:** both DAGs now use `airflow.sdk` (`Asset` replaces `Dataset`, plus `DAG`, `dag` and `task`). `BashOperator` and `PythonOperator` come from `airflow.providers.standard`.
- **Requirements and README:** `requirements.txt` pins `apache-airflow==3.3.2` and adds `apache-airflow-providers-standard`. The README now says "asset" instead of "dataset".

**Two changes beyond renaming**
- **Watermark in `ingest_shipments`:** it used to read the previous watermark from the metadata DB, and Airflow 3 doesn't let tasks do that. It now takes the highest `updated_at` from batch files of earlier intervals only.
  - A retry or clear of any interval rebuilds the same batch rather than an empty one.
  - The batch is written to a temp file and renamed, so a failed write can't leave a partial batch.
  - Across several runs, plus a re-run of an interval that already had a batch, I got 153 rows with no duplicate `event_id`. That matches the 153 events in `data/carrier_events.csv`.
- **`_READY` contents:** in Airflow 3, `xcom_pull(key=...)` only looks at the current task, so `_READY` came out as `carriers=None shipments=None`. I added `task_ids="build_scorecard"` to both pulls.

I also made the schedule `CronDataIntervalTimetable("@hourly")` instead of the bare string. Airflow 3 would otherwise treat `"@hourly"` as a point-in-time trigger, which changes `data_interval_end` and the batch file names.

**Before Monday**
- The watermark is now derived from files under `output/warehouse/shipments/`. Production needs that directory to persist, and the existing batches have to be in it when the new code first runs. If that directory is empty, the first run would reload every event.
- I couldn't test the Dataset-to-Asset trigger between the two DAGs, because `dag.test()` doesn't run the scheduler. Check in staging that a completed `ingest_shipments` run triggers `carrier_scorecard`.
- Production's existing metadata DB, with its old dataset URIs and XCom history, goes through `airflow db migrate`, which I didn't run.