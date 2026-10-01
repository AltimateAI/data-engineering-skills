The `inventory_snapshot` DAG now runs on Airflow 3.3.2. I ran it with `dag.test()` for 2026-03-06 and 2026-03-07 in the 3.3.2 venv, and both runs succeeded.

The changes are in `dags/inventory_snapshot.py` and `requirements.txt`:
- **Imports:** `DAG` and `get_current_context` now come from `airflow.sdk`, and `PythonOperator` comes from `airflow.providers.standard`.
- **DAG arguments:** `schedule_interval` is now `schedule`, and `provide_context=True` is gone.
- **Date values:** `execution_date` and `prev_ds` no longer exist in the Airflow 3 context. `build_snapshot` now takes `logical_date`, which is the same value `execution_date` held, and derives `ds`, `prev_ds` and the end-of-day cutoff from it. The audit task reads `logical_date` as well.
- **XCom pulls:** In Airflow 3, `xcom_pull` with no `task_ids` only looks at the current task. Left alone, the audit task would have written `null` for `sku_count` and `low_stock`, and the run would still have shown as successful. Both pulls now name `task_ids="build_snapshot"`.
- **`requirements.txt`:** pinned to `apache-airflow==3.3.2` and added `apache-airflow-providers-standard`, which the new operator import needs.

**Output format:** the two test runs wrote the CSV and audit JSON with the same columns, sorted keys and `change` logic as before. I couldn't run the old 2.11 version here, so I didn't diff the files against real production output. A quick comparison on your cluster after deploy would be worth doing.

I deleted the test outputs and the stray `airflow.cfg` the run created, so the working tree only has the two edits. I haven't committed anything.