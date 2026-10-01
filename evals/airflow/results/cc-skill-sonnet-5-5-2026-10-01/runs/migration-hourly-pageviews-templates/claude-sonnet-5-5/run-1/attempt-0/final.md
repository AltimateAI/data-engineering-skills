`hourly_pageviews` now loads and runs on Airflow 3.3.2, and the run at 10:00 UTC still processes 09:00–10:00. The output file names, marker names and contents are unchanged.

You were right that ruff wasn't enough. It renamed `schedule_interval` and moved the imports. It missed three things:

- **Schedule meaning:** on Airflow 3 a bare `"0 * * * *"` stops meaning "the previous hour". Every run would have processed the wrong hour and written files like `20260305T10.csv` instead of `T09`. I switched to `CronDataIntervalTimetable("0 * * * *", timezone="UTC")`, which keeps the old behaviour.
- **Removed template keys:** `execution_date`, `next_execution_date`, `prev_execution_date` and `yesterday_ds_nodash` would only have failed when a task rendered. They are now `data_interval_start` and `data_interval_end`. The previous hour and the previous day are computed from `data_interval_start`, and the marker name is built from it too (`%Y%m%dT%H0000`, the same as the old `ts_nodash`).
- **`catchup=False`:** it was already explicit, so I left it.

I also pinned `apache-airflow==3.3.2` and added `apache-airflow-providers-standard==1.19.0` in `requirements.txt`, since the DAG now imports from it.

What I ran:
- **Schedule check:** the first five run dates, logical dates and data intervals match the Airflow 2 behaviour. I captured that baseline with the 2.x scheduler defaults switched back on, since there's no 2.x environment here.
- **Test runs:** I ran `airflow dags test` twice, on a throwaway Airflow home, and all three tasks succeeded each time.
  - **Files:** it wrote `20260305T08.csv` and `20260305T09.csv`, plus `20260305T080000.done` and `20260305T090000.done`.
  - **Marker contents:** the markers read `hour=2026-03-05T09:00 staged=53`.
  - **Change column:** `views_change` for 09:00 was filled in from the 08:00 file.
  - **Cleanup:** it deleted the previous day's staging file and kept the same day's.
  - **Cleanup of my own output:** I removed the scratch output and scratch directories afterwards.

Not verified:
- **No real scheduler:** I did not run one.
- **Manual or API triggers:** a run triggered that way on Airflow 3 can have no logical date or data interval, so the templates would render empty. The README only describes scheduled runs, so I left it. Say if you want a fallback to the run time.
- **No tests:** the repo has no test suite.
- **Ruff style warning:** `ruff --select AIR` still reports AIR001, which wants the task variables named like their task ids. I left those as they are.