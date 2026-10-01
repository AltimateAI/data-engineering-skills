`warehouse_load` now imports with no variables configured at all, and its scheduled runs write the same rows as the old Airflow 2 code. I haven't committed anything; the only change is in `dags/warehouse_load.py`.

## Why it said the variable didn't exist
The problem isn't the variable. It's where the file reads it. `WAREHOUSE_DIR = Path(Variable.get("warehouse_path"))` runs at module level, so it executes every time the file is parsed. Airflow 2 parsed DAG files with direct access to the metadata DB, so that worked. Airflow 3 parses DAG files with no access to Variables, so the lookup fails with `VARIABLE_NOT_FOUND` even though the variable exists. `airflow variables get` reads the DB directly, which is why it finds it. That's also why CI, with no variables at all, fails the same way.

## What I changed
- **Variable read moved into the tasks.** `load_warehouse` and `validate_load` now call `Variable.get("warehouse_path")` when they run. The location still comes from the variable in each environment, and nothing reads it at parse time.
- **`schedule_interval` → `schedule=CronDataIntervalTimetable("0 6 * * *", timezone="UTC")`.** Airflow 3 removed `schedule_interval`, so that line would have been the next import error. A bare cron string isn't a drop-in replacement either: on 3.x it would make each 06:00 run load *that same* day instead of the previous day, with no error. The interval timetable keeps the old behaviour (the 06:00 run loads the previous day). `catchup=False` and all four steps are unchanged.
- **Manual triggers still pick a date.** On Airflow 3 a manual trigger has no `ds`. Without a fix, a manual run would filter on `None`, load nothing, and still report success. The tasks now fall back to the trigger date, which is what a manual run used on Airflow 2.

## How I checked it
- **Import, CI-style:** with a fresh metadata DB and zero variables, `airflow dags list-import-errors --local` reports nothing and both DAGs appear in `dags list`.
- **Schedule:** the next 5 run times and dates match what the Airflow 2 scheduler rules produce for the old DAG.
- **Real runs:** I ran 3 scheduled runs (loading 2026-03-02 to 03-04) on both the old code and the new code. The `daily_revenue` table came out identical. The `.duckdb` files differ byte-for-byte, but every row is the same.
- **Manual trigger:** a manual run on 2026-03-04 succeeded and reloaded that day's rows without creating duplicates. I couldn't compare it to the old code, because the old code crashes on a manual trigger under 3.x.

The repo's other DAG, `order_status_report`, was already written for Airflow 3, so I left it alone.

ruff still flags one thing: `aggregate_revenue` returns a `dict`, so Airflow also stores each region as its own XCom entry. It worked the same way on Airflow 2 and is harmless, so I didn't touch it.

`airflow dags list-import-errors --local` failed in your existing `AIRFLOW_HOME` with "Database migration required". If the new box shows that too, run `airflow db migrate` there first.