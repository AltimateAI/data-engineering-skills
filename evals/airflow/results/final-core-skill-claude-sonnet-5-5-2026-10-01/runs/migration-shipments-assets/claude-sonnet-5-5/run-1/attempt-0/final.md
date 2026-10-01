Both DAGs now import and pass the checks on Airflow 3.3.2. I did not run `carrier_scorecard`, so its output and `_READY` file are untested. Nothing is committed.

**What I changed**
- **`ingest_shipments`:**
  - **Schedule:** the bare `"@hourly"` now uses a `CronDataIntervalTimetable("0 * * * *")`, so batch names and interval ends are the same as on 2.x. `catchup=False` was already explicit, so I left it.
  - **Exactly-once watermark:** it was read straight from the metadata DB, which raises `RuntimeError` on a 3.x worker. It now comes from the same task's earlier XCom (`xcom_pull(..., include_prior_dates=True, map_indexes=-1)`). Without `map_indexes=-1`, a plain pull returns a list from the 3rd run on, which would reload old events.
  - **Manual trigger:** a manual trigger has no data interval on 3.x, so the task would have crashed. It now uses the hour of the trigger time, which is what 2.x did.
- **`carrier_scorecard`:**
  - **XCom pull:** the `_READY` template pulled XCom with no `task_ids`, which returns nothing on 3.x. It now names `build_scorecard`, so the `_READY` text should come out the same.
  - **Rename:** I renamed the Python function to `compute_scorecard` so the task variable can match its `task_id`.
- **Imports and pins:** `Dataset` is now `Asset` and the imports are on the new paths. `requirements.txt` pins `apache-airflow==3.3.2` and adds `apache-airflow-providers-standard`.

**What I checked**
- `airflow_check` exits 0, and the AIR lint rules are clean.
- The next five scheduled run dates, intervals and `catchup` for both DAGs match the 2.x behaviour (`compare_previews` exit 0).
- I replayed four consecutive hourly runs plus one manual trigger on the migrated copy. All five succeeded.
- Across those five batches there are no duplicate `event_id`s. Row counts match the source: 63 events through the 21:00 run, 153 through the 09:00 manual run.

**What I could not verify**
- **No true 2.x baseline:** there is no 2.x environment here, and the original watermark code fails on 3.x, so the replay was not a before/after comparison of output files. The row counts above are the evidence.
- **Scorecard not run:** an asset-triggered DAG can't be replayed. My direct run of it failed because the airflow environment needed `airflow db migrate`, and I stopped there. I only confirmed it imports. The scorecard CSV and `_READY` changes are small, but please run it once on staging before Monday.