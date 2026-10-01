I fixed the DAG: it now imports even with no variables configured, and a full test run succeeded. The change is in `dags/warehouse_load.py` only.

## What was going on

The DAG read `Variable.get("warehouse_path")` at the top of the file, so the lookup happened while Airflow was loading the file, not when a task ran. In Airflow 2, file loading could reach the metadata database, so this worked. In Airflow 3 it can't: variables are only available while a task is running. So the variable exists, but the code asks for it before Airflow can provide it. CI hits the same error for the same reason, not because it has no variables.

There was a second problem behind the first. `schedule_interval` was removed in Airflow 3, so once the variable error was gone the file would still have failed to import.

## Changes

1. **Variable read moved into the tasks.** A small helper, `_warehouse_db()`, reads `warehouse_path` when it's called. `load_warehouse` and `validate_load` each call it when they run. The location still comes only from that variable, so each environment keeps its own value.
2. **`schedule_interval="0 6 * * *"` → `schedule="0 6 * * *"`.** It still runs daily at 06:00. The start date, catchup setting, tags and all four steps (extract → aggregate → load → validate) are unchanged.

## How I checked it

In a throwaway Airflow home:
- With no variables set, `airflow dags list-import-errors --local` reported "No data found", meaning no import errors. This is the same situation as CI.
- With `warehouse_path` set, `airflow dags test warehouse_load 2026-03-01` finished with all tasks in `state=success`.
- The DuckDB table held amer 1165.42, apac 533.38 and emea 670.28 for 2026-03-01. Those match what I calculated directly from `data/orders.csv`.
- Airflow reports the schedule as `0 6 * * *`.

My first test attempt accidentally wrote an `airflow.cfg` into the repo; I deleted it, so the repo is clean apart from the DAG change.

After deploying, any task that runs without `warehouse_path` set will fail with a clear "variable not found" error. That's better than the whole DAG disappearing, but the variable still needs to be set in each environment where the DAG actually runs.