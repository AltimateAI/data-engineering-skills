The DAG is upgraded and runs on 3.3.2 in the venv. I ran it with `airflow dags test` for 2026-02-25 and 2026-02-26 and it succeeded. The 26th's `change` column was computed against the 25th's snapshot.

I couldn't run the old 2.11 code here, so I haven't diffed the outputs against it. The CSV and audit-JSON code is untouched, and the column order and JSON keys are the same. The `change` column and the cutoff for which movements count both rely on the day values I rebuilt (see below).

**What changed in `dags/inventory_snapshot.py`:**
- **Imports:** `DAG` now comes from `airflow.sdk`, and `PythonOperator` from `airflow.providers.standard.operators.python`.
- **Schedule:** `schedule_interval` became `schedule`, and `provide_context=True` is gone.
- **Day values:** Airflow 3 removed `execution_date` and `prev_ds`. Both tasks now take `data_interval_start`, which is what `execution_date` was for these scheduled daily runs. The day string, the previous day's snapshot name and the end-of-day cutoff are all derived from it.
- **Cutoff and manual runs:** I kept the cutoff as start plus one day instead of using `data_interval_end`. Manual runs in Airflow 3 have `data_interval_end` equal to the start, which would have produced empty snapshots.
- **XCom pulls:** the audit task's pulls now name `task_ids="build_snapshot"` explicitly. Airflow 3 no longer guarantees the old implicit behaviour.
- **`requirements.txt`:** pinned to `apache-airflow==3.3.2`.

**Before you deploy:**
- The new cluster needs `apache-airflow-providers-standard` installed. The venv here has it, but I didn't add it to `requirements.txt` because it comes in as a dependency of `apache-airflow` 3.3.2.
- Previously, `prev_ds` was the previous scheduled run's date. Now it is always the day before. That is the same thing for a daily schedule, but it would differ if a run were ever skipped.

I deleted the scratch Airflow home and output files from my test runs, so the working tree only has the two modified files.