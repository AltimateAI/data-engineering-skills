I added a pytest suite under `tests/`. `pytest tests/ -q` gives 9 passed on the current code in about 1.6s, using only the venv's Airflow 3.3.2 (no scheduler, webserver or services). I didn't change any DAG files, and `git status` shows only the new `tests/` directory.

**Files**
- `tests/conftest.py` sets up a throwaway Airflow home and DB, and a `dagbag` fixture.
- `tests/test_dag_integrity.py` covers loading and policy.
- `tests/test_orders_ingest.py` covers the pipeline order.

**Rules and the tests that cover them**
- **Files must load:** `test_no_import_errors` fails on any import error, and a cycle also lands in the DagBag's import errors. Two more tests catch a DAG that quietly stops being defined: `test_every_dag_file_defines_a_dag` and `test_expected_dags_present`.
- **Tag required:** `test_every_dag_has_a_tag`.
- **Catchup off:** `test_catchup_disabled`.
- **Real owner:** `test_task_owner_is_real` checks every task and fails on `airflow` or an empty owner.
- **At least 2 retries:** `test_task_retries_at_least_two` checks every task, so a task-level override is caught.
- **Pipeline order:** `test_pipeline_order` checks the exact upstream and downstream tasks of each step, so any reorder, skipped step or extra edge fails.

**Mutation check**
I planted 8 bugs in the DAGs, one per rule plus an import-time failure, and the suite caught 7. The tool restored the files afterwards.

The one it missed was an `import nonexistent_mod_xyz` inside a task function body. That only fails when the task runs, not when the DAG parses, so the suite can't see it. That is outside what you asked for, and catching it would need end-to-end tests that run the DAGs.

**Maintenance:** `EXPECTED_DAG_IDS` in `test_dag_integrity.py` lists the three current DAGs. Add new DAG ids there so deleting one fails CI.

**Not verified:** actually running the DAGs (the tests check structure only), and any Airflow version other than 3.3.2.