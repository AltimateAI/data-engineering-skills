The `hourly_pageviews` DAG now runs on Airflow 3.3.2. I ran it with `airflow dags test` for 2026-03-05T09:00 and all three tasks succeeded. The run wrote `20260305T09.csv`, `20260305T090000.done` containing `hour=2026-03-05T09:00 staged=53`, and the staging file. Those names and contents match the README.

Ruff alone wouldn't have caught the first three changes below, which change behaviour even though the DAG still imports.

- **Schedule:** I replaced `schedule_interval="0 * * * *"` with `schedule=CronDataIntervalTimetable("0 * * * *", timezone="UTC")`. In Airflow 3 a plain cron string becomes a trigger-style schedule, where the logical date is the moment the run fires. Without the explicit timetable, the 10:00 run would have written `…T10.csv` and `…T100000.done` instead of `…T09…`.
- **Removed template variables:** `execution_date`, `next_execution_date`, `prev_execution_date` and `yesterday_ds_nodash` no longer exist, so I rewrote the templates in terms of `logical_date`.
  - The hour is now `logical_date`, the end is `logical_date.add(hours=1)`, and the previous hour is `logical_date.subtract(hours=1)`.
  - The staging cleanup date is now `logical_date.subtract(days=1)`.
  - I used `logical_date` rather than `data_interval_start` on purpose. For manual runs Airflow 3 sets the interval to the hour before the logical date. My first attempt with `data_interval_start` wrote `T08.csv` next to a `T090000.done` marker, which would have broken the dashboard loader. This version keeps the old behaviour for scheduled and manual runs.
- **Imports:** `PythonOperator` and `BashOperator` now come from `airflow.providers.standard`. `DAG` comes from `airflow.sdk`. The standard provider is already installed in the venv.
- **`requirements.txt`:** I changed `apache-airflow` from 2.11.2 to 3.3.2.

Runs triggered by an asset have no `logical_date`, so these templates would fail for them. This DAG only has a time schedule, so it doesn't matter today.

I removed the `airflow.cfg`, the temporary Airflow home and the test output, so only `dags/hourly_pageviews.py` and `requirements.txt` are changed. I haven't committed anything.