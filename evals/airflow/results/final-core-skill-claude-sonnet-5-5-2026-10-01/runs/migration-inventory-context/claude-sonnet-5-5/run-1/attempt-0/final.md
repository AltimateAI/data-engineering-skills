The `inventory_snapshot` DAG now imports and runs on Airflow 3.3.2. The scheduled and manual replays succeeded, but I couldn't compare the CSV and JSON output byte-for-byte against the old code. There's no 2.x environment here, so the 2.x code had no baseline run.

**What I changed in `dags/inventory_snapshot.py` and `requirements.txt`:**
- **Schedule:** a bare `timedelta(days=1)` fires on a different day under 3.x, which would have shifted every snapshot and audit file by one day. I wrapped it in `DeltaDataIntervalTimetable`, so each run still snapshots the same day, with the same file names. `catchup=False` was already explicit, so I left it. `start_date` is now a fixed UTC `pendulum` date.
- **Removed context keys:** `execution_date`, `ds` and `prev_ds` no longer exist in 3.x. A small `_run_days()` helper now builds them from `logical_date` and `dag_run`. The "previous day's snapshot" lookup behaves as before.
- **Audit XCom:** the audit task pulled `sku_count` and `low_stock` without naming the producing task, which returns `None` on 3.x. Both pulls now name `build_snapshot`, so the audit JSON keeps its values.
- **Imports and operator arguments:** `PythonOperator` now comes from the standard provider and `DAG` and `get_current_context` from `airflow.sdk`. I removed `provide_context=True`.
- **Renames:** I renamed the callables to `write_snapshot` and `write_audit`, and the task variables to match their task ids. Task ids, task order and output paths are unchanged.
- **Requirements:** pinned `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.

**What I checked:**
- The Airflow checker reports 0 import errors and 0 errors, and `ruff --select AIR` is clean.
- The first 5 scheduled run dates, logical dates and intervals match what 2.x would produce.
- I replayed 3 consecutive scheduled runs plus one manual trigger on the migrated DAG. All succeeded and wrote `output/inventory/<day>.csv` and `output/audit/<day>.json`.
- I only skimmed the output (one audit JSON and the head of one CSV, which looked sensible), not a diff against the old code.

**One decision for you:**
- **Manual triggers:** the checker still warns about them. A manual run has no logical date on 3.x, so I use the trigger date and keep 2.x's quirk where `prev_ds` equals `ds`. The README doesn't say how this DAG is triggered by hand. If it never is, this is harmless.

**Not done:** the repo has no tests, so I didn't add any.