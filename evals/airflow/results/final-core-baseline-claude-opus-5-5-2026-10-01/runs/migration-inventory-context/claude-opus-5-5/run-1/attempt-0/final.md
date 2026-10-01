The `inventory_snapshot` DAG now runs on Airflow 3.3.2 and writes exactly the same snapshot CSVs and audit JSON files as before. I ran it with `dag.test()` for 12 days (2026‑02‑19 to 2026‑03‑02) and compared the results to output from the old code over the same days. All 24 files (12 CSVs, 12 audit JSONs) were byte-identical, and the DAG loads with no import errors. I haven't committed anything.

The changes are in `dags/inventory_snapshot.py` and `requirements.txt`. Several of them fix problems that wouldn't have raised an error in 3.x but would have changed what alerting reads:

- **Date semantics (most important):** in 3.x, a plain `timedelta` schedule defaults to a different timetable. Each run's date becomes the end of the day instead of the start, so every file name and stock cutoff would have moved one day later. I set the timetable explicitly to `DeltaDataIntervalTimetable(timedelta(days=1))` so the dates stay the same as on the old cluster.
- **`execution_date` and `prev_ds` were removed:** both now come from `logical_date`, the 3.x replacement. Without the `prev_ds` fix, the `change` column would have been empty in every CSV. The previous snapshot is still taken as the previous calendar day.
- **Audit XCom reads:** in 3.x, `xcom_pull` with no `task_ids` only looks at the calling task's own values, so `sku_count` and `low_stock` would have been `null` in the audit JSON. Both pulls now name `task_ids="build_snapshot"`.
- **Mechanical updates:**
  - Imports now come from `airflow.sdk` and `airflow.providers.standard`.
  - `schedule_interval` became `schedule`.
  - `provide_context` was removed.
  - `start_date` is now explicitly in UTC.
  - `requirements.txt` pins `apache-airflow==3.3.2`.

**Triggering by hand:** in 3.3, a manual run can be started with no logical date (for example through the API), and this DAG will fail for such a run. It also had no meaningful date before, so trigger it with a logical date.