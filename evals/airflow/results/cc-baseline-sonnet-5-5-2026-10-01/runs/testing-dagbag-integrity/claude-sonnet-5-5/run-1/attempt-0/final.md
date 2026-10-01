I added a pytest suite under `tests/`, and `pytest tests/` passes on the current code (7 tests, about 2 seconds). It runs on the venv alone. It loads the DAGs through Airflow's `DagBag`, so it needs no scheduler, webserver or database.

- **`tests/conftest.py`** builds one `DagBag` over `dags/`. I turned off safe mode so every file is parsed, even one that doesn't mention "airflow" or "dag".
- **`tests/test_dags.py`** has the checks:
  - **Loading:** it fails if `dags/` is empty, if any file has an import error (cycles are reported as import errors too), or if any file produces no DAG.
  - **DAG policy:** every DAG needs at least one tag and `catchup=False`.
  - **Task policy:** every task needs an owner that isn't blank or `"airflow"`, and at least 2 retries. This checks the resolved task values, so it also catches a per-task override like `retries=0`.
  - **`orders_ingest` order:** the tasks must be exactly `extract_orders -> validate_orders -> load_orders -> publish_summary`, with no extra tasks or edges.

To confirm the tests fail when they should, I temporarily broke the DAGs one way at a time and ran the suite each time. Each break failed the test that targets it:
- a file that imports a missing module
- a dependency cycle
- the owner set to `airflow`
- default retries lowered to 1
- a per-task `retries=0`
- `catchup=True`
- empty tags
- a reordered `orders_ingest`

I reverted every break, and the DAGs are unchanged. `git status` shows only the new `tests/` directory.

While doing that, a bad backup command of mine deleted `dags/` for a moment. I restored it with `git checkout -- dags` and confirmed the files match the original commit. I then redid the checks above using git for the restore.

Airflow 3.3 moved `DagBag`, so the suite imports it from `airflow.dag_processing.dagbag`. The old `airflow.models.dagbag` path is deprecated.