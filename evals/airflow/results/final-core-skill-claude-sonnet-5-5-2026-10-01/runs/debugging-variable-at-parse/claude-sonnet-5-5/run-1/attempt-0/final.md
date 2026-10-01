`dags/warehouse_load.py` now imports cleanly, with no variables configured and no Airflow connection. The DAG ran end to end with `airflow dags test`: all four tasks succeeded and wrote the expected rows to DuckDB.

**What was wrong**
- **The variable lookup:** `Variable.get("warehouse_path")` was at module level, so it ran every time the file was parsed. In 3.x the parser has no Variable backend, so you get `VARIABLE_NOT_FOUND`. That's why it fails in CI and under `list-import-errors --local` even though `airflow variables get` works against your real deployment.
- **A second error behind it:** `schedule_interval=` was removed in Airflow 3 and would have raised a `TypeError` as soon as the first problem was fixed.

**What I changed**
- **Variable read:** `warehouse_path` is now read inside the tasks through a small `_warehouse_dir()` helper. It still comes from the variable in each environment. I also removed the `WAREHOUSE_DIR` and `WAREHOUSE_DB` module constants.
- **Schedule:** `schedule_interval="0 6 * * *"` is now `schedule=CronDataIntervalTimetable("0 6 * * *", timezone="UTC")`. A bare cron string in 3.x would have shifted `ds` to the run's firing day, so every run would have loaded a different day than the 2.x box did. The timetable keeps the 2.x behaviour. `catchup=False` is unchanged.
- **Manual triggers:** `ds` is empty on a manual trigger in 3.x, so `_run_day` falls back to the trigger date, which is what 2.x used.
- **Unchanged:** the four tasks, their dependencies and the cron time.

**Testing**
- I ran `airflow dags list-import-errors --local` and `airflow dags test warehouse_load 2026-03-02` against a scratch Airflow home with `AIRFLOW_VAR_WAREHOUSE_PATH` set. That run loaded rows for amer, apac and emea on 2026-03-02. I deleted the scratch directory afterwards.
- I did not run the skill's replay comparison against the old 2.x output, because there is no 2.x environment here. The fire dates and the manual-trigger behaviour are therefore checked against the documented 2.x behaviour, not a real before-and-after run.
- `dags test` also isn't a real scheduled run. Check the first scheduled run on the new box.

`dags/order_status_report.py` has the same schedule problem: a bare `"0 5 * * *"` fires on a different day under 3.x than it did under 2.x. You didn't ask about it, so I left it alone. Say so if you want it fixed too.