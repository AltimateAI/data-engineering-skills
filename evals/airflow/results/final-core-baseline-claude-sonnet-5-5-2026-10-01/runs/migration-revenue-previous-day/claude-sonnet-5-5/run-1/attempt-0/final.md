The repo now imports and tests cleanly on Airflow 3.3.2 (`pytest tests/` gives 2 passed). I couldn't run 2.11 here, so I haven't diffed old and new output.

I rendered the SQL for the 2026-03-03 business day and ran it against `data/orders.csv`. It returned APAC 2 / 285.46, EMEA 2 / 320.10 and NA 5 / 924.05. I also ran `airflow dags test daily_revenue 2026-03-03T04:15:00` end to end. Both tasks succeeded and the manifest was written, but that CSV was header-only (see the last point below). I deleted the generated `output/` and `airflow.cfg`.

**`daily_revenue`**
- **Schedule:** In Airflow 3, `schedule="15 4 * * *"` becomes a trigger-style timetable. A run at 04:15 on day D would then get `ds = D` instead of D-1, so every report would be for the wrong day. I set `schedule=CronDataIntervalTimetable("15 4 * * *", timezone="UTC")`, which keeps the 2.x behaviour: the run at 04:15 on D reports business day D-1.
- **Removed template variables:** `next_ds` is gone, so the SQL now uses `{{ data_interval_end | ds }}`. `execution_date` is gone, so the manifest uses `logical_date`.
- **Imports and arguments:** `DAG` now comes from `airflow.sdk`, the operators from `airflow.providers.standard`, and `schedule_interval` became `schedule`.

**`region_reference`**
- `DummyOperator` became `EmptyOperator`, and `days_ago(1)` became a fixed `start_date` of 2026-01-01 UTC.
- `schedule_interval=None` became `schedule=None`.

**Tests and requirements**
- `DagBag` moved to `airflow.dag_processing.dagbag` and no longer accepts `include_examples`, so I updated the import and constructor call in `tests/test_dag_integrity.py`.
- `get_dag()` now needs a metadata database, so the test reads `dagbag.dags` instead.
- `requirements.txt` pins `apache-airflow==3.3.2`, and `duckdb` goes from 1.4.4 to 1.5.6 to match the venv. That is a minor duckdb bump. I only checked the revenue query's output on 1.5.6, so confirm against 1.4.4 if you want that ruled out.

**Before cutover**
- **Scheduled vs manual runs:** I verified the scheduled-run logic, which is what Finance depends on. A manual or test run with logical date X uses the window [X, X), so it returns no rows and writes a header-only CSV. I believe 2.x does the same for manual runs, but I couldn't confirm that.
- **Manifest timestamp format:** The manifest `logical_ts` printed as `2026-03-03 04:15:00+00:00`. I'm not sure that matches what 2.11 wrote, so check it against an existing manifest the dashboard reads.
- **README example:** The `airflow dags test daily_revenue 2026-03-04` example now yields an empty report, so a date inside the data range won't show numbers. I left it unchanged. Say if you want it reworded.

I haven't committed anything.