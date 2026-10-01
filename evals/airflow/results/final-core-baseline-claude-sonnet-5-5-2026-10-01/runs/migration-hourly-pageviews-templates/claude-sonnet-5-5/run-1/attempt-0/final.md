The `hourly_pageviews` DAG now parses and runs on Airflow 3.3.2, and the output files and `.done` markers keep the names and contents the README describes. Ruff alone would have missed the scheduling change, which is the one that mattered most.

I tested with `dag.test()` in the 3.3.2 venv, using manual runs with `logical_date` set to 09:00 and 10:00 on 2026-03-05. The 10:00 run staged 53 events for hour 09 and wrote `20260305T09.csv` and `20260305T090000.done` with `hour=2026-03-05T09:00 staged=53`. The 09:00 run staged 43 events for hour 08. The CSV has the usual `page,views,sessions,views_change` columns, and `views_change` is filled from the previous hour's file.

I did not wait for a live scheduler tick. I checked scheduled runs by asking the timetable for the next run, which gave a 10:00 logical date covering 10:00–11:00.

**Changes**
- **Scheduling:** I replaced `schedule_interval="0 * * * *"` with `schedule=CronDataIntervalTimetable("0 * * * *", timezone="UTC")`. A plain cron string in Airflow 3 means "run at that moment", with no data interval. The 10:00 run would then have processed the wrong hour, and the file and marker names would have been off by one hour. The explicit timetable keeps the 10:00 run covering 09:00–10:00.
- **Templates:** I replaced the removed variables with `data_interval_start` and `data_interval_end`.
  - `execution_date` and `next_execution_date` became `data_interval_start` and `data_interval_end`.
  - `prev_execution_date` became `data_interval_start.subtract(hours=1)`.
  - `ts_nodash` and `yesterday_ds_nodash` are now spelled out from `data_interval_start`, so the marker name and the staging cleanup are unchanged.
- **Imports:** `DAG` now comes from `airflow.sdk`, and the operators from `airflow.providers.standard`.
- **`requirements.txt`:** I pinned `apache-airflow==3.3.2`.

Ruff's remaining `AIR001` warnings only ask for task variable names to match the `task_id`. I left them alone.

**Behaviour change:** manual runs now get their interval from the logical date you pick, so a manual run at logical date 10:00 processes 09:00–10:00. Scheduled runs are unaffected.

I deleted the temporary Airflow home and `output/` directory used for testing, so the only changes in the tree are `dags/hourly_pageviews.py` and `requirements.txt`.