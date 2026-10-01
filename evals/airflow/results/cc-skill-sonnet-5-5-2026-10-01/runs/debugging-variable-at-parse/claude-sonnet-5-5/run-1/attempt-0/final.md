`warehouse_load` now imports with the variable set and with no variables at all. I ran it end to end and all four tasks succeeded. The only file I changed is `dags/warehouse_load.py`.

**Why it failed.** The DAG file had `Variable.get("warehouse_path")` at module level. On Airflow 3, DAG files are parsed in an isolated process with no access to the metadata DB. A parse-time `Variable.get` can't see your variable, which is why `airflow variables get` works and the import doesn't. In CI the variable genuinely doesn't exist, so it failed the same way. Variable reads only work inside a running task.

**What I changed:**
- **Variable lookup:** `WAREHOUSE_DIR` and `WAREHOUSE_DB` are gone, replaced by a small `warehouse_dir()` helper that reads `warehouse_path`. `load_warehouse` and `validate_load` call it when they run, so the location still comes from the variable in every environment.
- **Schedule:** `schedule_interval="0 6 * * *"` became `schedule=CronDataIntervalTimetable("0 6 * * *", timezone="UTC")`.
  - A plain cron string on Airflow 3 changes what `ds` means. The 06:00 run on the 2nd would load the 2nd instead of the 1st, with no error.
  - The interval timetable keeps the Airflow 2 behaviour: each run still processes the previous day.
- **Start date:** the naive `datetime(2026, 1, 1)` is now `pendulum.datetime(2026, 1, 1, tz="UTC")`.
- **Unchanged:** all four tasks, their dependencies, `catchup=False`, and the 06:00 schedule.

**Checks I ran:**
- The skill's import checker exits 0 with 0 errors, and `airflow dags list-import-errors --local` reports none with the variable set or unset.
- `airflow dags test warehouse_load 2026-03-02T06:00:00+00:00` against a throwaway Airflow DB and a throwaway DuckDB file succeeded. It wrote `daily_revenue` rows for amer, apac and emea, and the temp files are cleaned up.

**What I couldn't check:**
- I had no Airflow 2 environment, so I didn't diff before and after schedules. The check is by reasoning plus the checker's run preview.
- A `dags test` run with a bare date uses that date as `ds`. That is a quirk of `dags test`, not a bug. Real scheduled runs load the previous day.
- A manually triggered run would have no `ds` on Airflow 3. Your README doesn't mention manual runs, so I left that alone.

`dags/order_status_report.py` also uses `ds`. It currently gets a `CronTriggerTimetable`, so its `ds` is the day it fires, and I left it alone since it wasn't part of your request. If it ran on a bare cron string in Airflow 2 and was meant to process the previous day, it will be off by one and needs the same timetable fix.