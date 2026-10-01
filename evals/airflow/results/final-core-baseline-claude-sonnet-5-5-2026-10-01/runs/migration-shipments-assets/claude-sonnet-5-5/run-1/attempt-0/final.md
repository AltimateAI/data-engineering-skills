Both DAGs now import and run on Airflow 3.3.2. I ran them with `airflow dags test` against a throwaway metadata DB, not a scheduler or production, and I haven't committed anything.

**Changes**
- **`dags/ingest_shipments.py`**
  - **Watermark:** the old code queried the `XCom` table directly through a DB session, which Airflow 3 doesn't allow inside task code. The task now reads the previous watermark with `ti.xcom_pull(..., include_prior_dates=True)`.
  - **Schedule and imports:** `schedule_interval="@hourly"` became `schedule=CronDataIntervalTimetable("@hourly", timezone="UTC")`, and the imports now come from `airflow.sdk`.
  - **Why that timetable:** Airflow 3's plain `"@hourly"` string defaults to a different timetable. Pinning this one keeps the same data interval, so the upper bound and the `batch_<interval end>.csv` names don't change.
- **`dags/carrier_scorecard.py`**
  - **Imports:** it uses `airflow.sdk` (`DAG`, `Asset`) and the standard-provider `BashOperator` and `PythonOperator`.
  - **`_READY` template:** the `ti.xcom_pull` calls now name `task_ids="build_scorecard"` explicitly, so the `_READY` text doesn't depend on Airflow's default pull behavior.
- **`Dataset` → `Asset`:** the asset URI `warehouse://shipments/batches` is unchanged.
- **`requirements.txt` and `README.md`:** `apache-airflow` is pinned to 3.3.2, and the README says "asset" instead of "dataset".

**What I checked**
- **Exactly-once load:** I ran two consecutive hourly intervals, 19:00 and 20:00 on 2026-03-04. Together they loaded 32 events, which matches the source rows up to that cutoff, with no event ID appearing in both batches.
- **Scorecard and `_READY`:** both were produced and have the expected format (`carriers=4 shipments=26`). I didn't diff them against output from the old 2.x code, because I only ran the migrated code. I didn't modify the scorecard logic itself.

**Before Monday**
- **Watermark history:** the new code pulls the last watermark from XCom through the task SDK. If production's existing Airflow 2 XCom rows aren't carried into the 3.3 metadata DB, the first run there will see no watermark and reload everything up to its interval end. Confirm the DB is migrated in place, or seed the watermark.
- **Clearing a run (not new):** the watermark mechanism already had this weakness before the migration. Clearing and re-running an old interval after later runs have loaded will overwrite that interval's batch file with fewer rows. Avoid doing that during reconciliation.