I added a pytest suite under `tests/`, and `pytest tests/` passes on the current code (10 tests, about 2 seconds). It needs only the Airflow venv, with no scheduler, webserver or database. I didn't touch the DAGs.

The suite is two files:
- **`tests/conftest.py`:** builds a `DagBag` over `dags/` once per run.
- **`tests/test_dag_integrity.py`:** holds the checks.

The checks are:
- **Loading:** `import_errors` must be empty, which covers import errors, cycles and parse failures. Each `.py` file in `dags/` must also produce at least one DAG, so a file that imports cleanly but defines no DAG fails too. There is also a check that `dags/` isn't empty.
- **Policy:** every DAG needs at least one tag and `catchup` off. Every task needs an owner that isn't `airflow` and at least 2 retries. These are checked on the task's effective values, so `marketing_spend.fetch_spend` with `retries=4` is read correctly.
- **`orders_ingest` order:** the DAG's task set must be exactly the four tasks. Each task must feed only the next one in `extract_orders → validate_orders → load_orders → publish_summary`, with no extra edges, and the chain must start at `extract_orders` and end at `publish_summary`.

To check the tests catch real problems, I ran them against a scratch copy with these changes:
- a DAG file with a bad import
- `catchup=True`
- an empty tag list
- `retries=1`
- owner set to `airflow`
- a skipped `validate_orders` step

Seven tests failed as expected, and I deleted the scratch copy afterwards.

`DagBag` now lives in `airflow.dag_processing.dagbag`. The old `airflow.models.dagbag` path still works in 3.3 but is deprecated.

I haven't committed anything, so the new `tests/` directory is untracked.