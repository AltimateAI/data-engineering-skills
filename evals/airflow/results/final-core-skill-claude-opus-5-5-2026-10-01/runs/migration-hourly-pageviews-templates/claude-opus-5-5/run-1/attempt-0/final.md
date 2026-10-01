The `hourly_pageviews` DAG is ready for Airflow 3.3.2. I replayed 19 scheduled hourly runs plus one re-run on both Airflow 2.11.2 and 3.3.2, and every hourly CSV, `.done` marker and staging file came out byte-for-byte the same. The ruff fixes alone were not enough: the DAG would have imported cleanly but processed the wrong hour or failed when tasks ran.

**What ruff missed (changes in `dags/hourly_pageviews.py`):**

1. **Schedule shift.** On Airflow 3 the bare string `"0 * * * *"` means "process the hour the run fires in" instead of "the hour that just ended." That would have moved every file and marker forward by one hour without any error. I changed it to `CronDataIntervalTimetable(SCHEDULE, timezone="UTC")`, so the 10:00 run still writes `20260305T09.csv` and `20260305T090000.done`. `catchup=False` stays as it was.
2. **Seven templates used variables Airflow 3 removed:** `execution_date`, `next_execution_date`, `prev_execution_date` and `yesterday_ds_nodash`. The tasks would have failed when they ran. They now all come from one helper, `run_hour(dag_run)`, which gives the start of the hour being processed. The "previous hour" comparison and the "delete yesterday's staging files" step are worked out from it exactly as before.
3. **Manual triggers:** on 3.x these have no date at all, so the old templates would fail. They now reprocess the latest finished hour (more on this below).
4. **Tidying:** task variables now match their task_ids (ruff's AIR001 rule), so the functions became `_extract_hour`/`_aggregate_hour`. Task ids, file paths, file names and contents are unchanged.

`requirements.txt` now pins `apache-airflow==3.3.2` and adds `apache-airflow-providers-standard==1.19.0`. The operators come from that package now.

**How I checked it:**
- The migration checker and `ruff --select AIR` are clean, and plain `ruff check` passes too.
- The upcoming run times and date ranges on 3.3 match what 2.x would have produced.
- The replay ran against a real Airflow 2.11.2 install on this machine (`agent-airflow-2.11`). It crossed midnight, so the step that deletes the previous day's staging files was exercised.
- There are no tests in the project, so none were run.

**Decision for you: manual triggers.** These now behave differently from 2.x. On 2.x, triggering at 12:23 wrote an empty `20260305T12.csv` for an hour that hadn't finished yet. It also wrote a misnamed marker, `20260305T122300.done`, containing `staged=0`, which the dashboard loader would presumably never pick up. The migrated DAG instead reprocesses 11:00–12:00 under the normal names (`20260305T11.csv`, `20260305T110000.done`). That looked like the useful behaviour, but if anything relied on the old manual-run output, tell me and I'll change it.

Nothing is committed yet.