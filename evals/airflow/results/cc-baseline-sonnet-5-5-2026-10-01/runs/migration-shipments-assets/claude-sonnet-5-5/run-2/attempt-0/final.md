Both DAGs now parse and run on the local Airflow 3.3.2. I ran them with `airflow dags test`, and the scorecard and `_READY` file came out in the same format as before. I haven't run the full chain end to end, so I haven't confirmed that a finished ingest run triggers the scorecard through the asset.

**`carrier_scorecard.py`**
- Imports now come from `airflow.sdk` (`DAG`, `Asset`) and the standard provider (`PythonOperator`, `BashOperator`). `Dataset` is now `Asset`, with the same URI.
- The `_READY` command used `ti.xcom_pull(key=...)` with no task id. In Airflow 3 that defaults to the current task, `mark_ready`, so the counts would have come out blank. It now names `task_ids="build_scorecard"`.

**`ingest_shipments.py`**
- The old DAG read its high-water mark by querying the `XCom` table directly. Airflow 3 blocks task code from querying the metadata database, so that would have failed.
- The mark is now the largest `updated_at` in batch files for earlier intervals. This lets a re-run of an interval reproduce its original batch instead of coming back empty or double-loading.
- The batch is written to a temp file and then renamed, so a failed run can't leave a half-written batch file.
- `schedule_interval` is now `schedule`, and the imports come from `airflow.sdk`.

**`requirements.txt`**: now pins `apache-airflow==3.3.2`.

**Testing**
- I ran the 19:00 and 20:00 intervals, then re-ran 19:00. The batch files had 15 and 17 rows, with no duplicate event IDs, and the re-run left the 19:00 batch unchanged.
- The scorecard step finished and wrote `carriers=4 shipments=26` to `_READY`.
- I deleted the test output and the scratch Airflow home afterwards, and nothing is committed.

**Differences to expect**
- On a manual trigger, Airflow 3 sets the data interval start and end to the same moment. Scheduled hourly runs aren't affected, but a manually triggered ingest will take its batch cutoff from the trigger time.
- The file-derived mark replaces the XCom value, so the first Airflow 3 run will find nothing in `output/warehouse/shipments/` if production's existing batches live elsewhere or were moved. It would then reload everything from the start. Confirm the existing batch files are still in that directory before Monday.