Both DAGs now run on Airflow 3.3.2. In a local test they loaded every event exactly once, and the batches, `carrier_scorecard.csv` and `_READY` came out byte-for-byte identical to the Airflow 2 logic. Nothing is committed yet.

**What had to change**

- **`ingest_shipments` watermark (the important one):** the DAG queried the XCom table directly with `provide_session`, and Airflow 3 tasks can no longer touch the metadata database. The watermark now comes from the batch files themselves: the latest `updated_at` already loaded. Since those files are what ops reconciles against, the two can't disagree.
- **`_READY` would have broken without any error:** `ti.xcom_pull(key=...)` with no `task_ids` now pulls from the calling task. The file would have read `carriers=None shipments=None`. I pointed it at `build_scorecard`.
- **Schedule:** `schedule_interval` was removed. A plain `"@hourly"` would also switch to a different default timetable and change the data intervals, so I set it explicitly to hourly intervals as before. Batch file names (`batch_<interval end>.csv`) stay the same.
- **Renames:** `Dataset` became `Asset` (same URI, so the scorecard still triggers), imports now come from `airflow.sdk` and the standard provider, and `requirements.txt` and the README are updated.

**Two exactly-once holes in the old design, now closed**

- If a run wrote its batch but then failed, the next hour reloaded the same events. Now batches are written all-or-nothing, and the watermark reflects what's actually in the warehouse.
- Clearing or re-running an interval that was already loaded used to overwrite its batch with a header-only file, losing those events. Now a run whose batch file already exists leaves it alone.

**How I tested it:** 10 hourly runs, each followed by a scorecard run. All 153 events loaded with no duplicates, and the output matched a replay of the original code exactly (`carriers=4 shipments=63`). Re-running an old interval and repeating the latest one changed no output files. I removed all test files afterwards.

**For Monday**

- Production needs `apache-airflow-providers-standard` installed (it's in `requirements.txt`).
- Production must use the same `output/warehouse/shipments` directory with the existing batches. The first Airflow 3 run picks up from those files, so no XCom state needs carrying over.
- If Airflow is down for a few hours during the switch, nothing is lost. The first run after the gap loads everything since the last batch into one file.

Want me to commit this on a branch and open a PR?