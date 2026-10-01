I fixed `dags/warehouse_load.py` so it imports without needing the variable. I haven't run the tasks or a full `airflow dags list-import-errors`, and I didn't check the DAG's cron schedule after the change.

**Why it failed.** The file called `Variable.get("warehouse_path")` at module level. In Airflow 3, DAG files are parsed in a sandbox that has no access to the metadata database or Variables. The lookup therefore fails with `VARIABLE_NOT_FOUND`, even though `airflow variables get warehouse_path` works from the CLI. Your CI has no variables at all, so it hit the same error.

**What I changed:**
- **Variable lookup:** the module-level `WAREHOUSE_DIR` and `WAREHOUSE_DB` are replaced by a `warehouse_dir()` helper. `load_warehouse` and `validate_load` call it when they run, so the location still comes from `warehouse_path` in each environment.
- **Schedule argument:** I changed `schedule_interval="0 6 * * *"` to `schedule="0 6 * * *"`. Airflow 3 removed `schedule_interval`, so it would have been the next import error once the variable one was gone. The cron expression is unchanged.
- **Steps and ordering:** all four tasks and their order are untouched.

**Check it:**
- **Import:** I imported the module with no variables configured and it succeeded.
- **CI:** it should now pass the import check. A task run will still need `warehouse_path` set, as it should.