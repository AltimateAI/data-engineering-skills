I fixed `dags/warehouse_load.py` so it imports with no variables configured, but I couldn't run the DAG end to end here.

**Cause.** The DAG called `Variable.get("warehouse_path")` at module level, so it ran every time the file was parsed. In Airflow 3, DAG files are parsed in a sandbox that can't read Variables, and the SDK reports that as `VARIABLE_NOT_FOUND`, not as a permissions problem. Your CLI call works because it runs in a different context, and CI fails because it has no variables at all.

**Changes.**
- **Variable lookup.** The module-level `WAREHOUSE_DIR` and `WAREHOUSE_DB` constants are replaced by a small `warehouse_dir()` helper. `load_warehouse` and `validate_load` call it when they run, so the path still comes from `warehouse_path` and can differ per environment.
- **Schedule argument.** `schedule_interval="0 6 * * *"` is now `schedule="0 6 * * *"`. Airflow 3 removed `schedule_interval`, so this would have been your next import error. The cron expression is the same, so the run time doesn't change.
- **Steps.** All four tasks and their wiring are unchanged.

**Testing.**
- **Import check.** I imported the module with no variables set and it succeeded. That is the CI scenario.
- **Run check.** `dag.test()` needs an initialised Airflow metadata DB, which I don't have here, so I haven't exercised the tasks. I'd run `airflow dags test warehouse_load 2026-03-01` on your new setup. The sample data in `data/orders.csv` includes 2026-03-01 rows.

**Task-time requirement.** `warehouse_path` now has to be readable when the tasks run. On a worker, an environment variable such as `AIRFLOW_VAR_WAREHOUSE_PATH` or your secrets backend works, as does a variable in the metadata DB. If the variable is missing, the task now fails at run time instead of the DAG failing to import.