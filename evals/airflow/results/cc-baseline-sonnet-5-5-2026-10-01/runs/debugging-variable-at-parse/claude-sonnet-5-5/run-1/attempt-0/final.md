`warehouse_load` now imports cleanly, but I haven't run it end to end. `DagBag('dags')` loads it with no import errors and no `warehouse_path` variable configured. I couldn't run a full `dag.test()`: the sandbox blocked creating a temp directory, and the test then failed because the local Airflow metadata DB has no tables.

**What was wrong:** The DAG file called `Variable.get("warehouse_path")` at module level, so it ran every time Airflow parsed the file. In Airflow 3 the DAG processor has no direct metadata-DB access, so a variable lookup at parse time goes through the SDK execution path. That path can't find your variable in the parsing environment, which is why it fails under `--local` and in CI even though `airflow variables get` works from your shell. Airflow 2 allowed the module-level call, which is why it worked on the old box.

**What I changed in `dags/warehouse_load.py`:**
- **Variable lookup:** The module-level `WAREHOUSE_DIR` and `WAREHOUSE_DB` constants are gone. A small `warehouse_dir()` helper now reads the `warehouse_path` variable when a task runs. `load_warehouse` and `validate_load` call it, so the location still comes from the variable in each environment.
- **Schedule argument:** `schedule_interval="0 6 * * *"` is now `schedule="0 6 * * *"`. Airflow 3 removed `schedule_interval`, and it would have been the next import error. The cron expression is unchanged, so the run time is the same.

All four tasks, their dependencies and the logic are untouched.

The variable is only needed when `load_warehouse` and `validate_load` run, so CI can import the DAG without it. To run those tasks in CI, set `AIRFLOW_VAR_WAREHOUSE_PATH` in the environment.