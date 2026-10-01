I've added the test suite under `tests/`. `pytest tests/` passes on the current code (12 passed in about 2 s), and I didn't touch anything in `dags/`: `git status` shows only the new `tests/` folder.

**What it checks**
- **`tests/test_dag_integrity.py`** – files that fail to load:
  - Fails if Airflow reports any load error, and prints which file failed and why. This covers import errors, cycles and invalid DAG definitions.
  - Fails if the set of DAG ids isn't exactly `customer_snapshot`, `marketing_spend` and `orders_ingest`. **When you add or remove a DAG on purpose, update `EXPECTED_DAG_IDS` in this file.**
  - Fails if any `.py` file in `dags/` produces no DAG. This catches the "vanished from the UI" case even when there's no error, e.g. someone deletes the final `orders_ingest()` call.
- **`tests/test_dag_policy.py`** – your policy, checked across every DAG and every task:
  - Every DAG has at least one tag and catchup turned off.
  - Every task has an owner that isn't empty or `"airflow"`, and at least 2 retries.
  - It reads each task's actual settings, so a single task that overrides the DAG-wide defaults (like `fetch_spend`'s `retries=4`) is still checked.
- **`tests/test_orders_ingest.py`** – each of the four steps must have exactly the expected step before and after it, so the order must be `extract_orders -> validate_orders -> load_orders -> publish_summary`. Reordering, skipping a step or inserting one between two steps all fail. Adding an extra task alongside the chain (one that doesn't break any of these links) is allowed.
- **`tests/conftest.py`** – sets Airflow up for the tests before it's imported: it points Airflow at `dags/` and gives each test run its own temporary Airflow home and SQLite database. No scheduler or webserver is needed.

**Proof the tests catch real breakage:** I made 11 deliberate one-line bugs in the DAGs, one at a time, and the suite failed on every one. The bugs included a bad import, a cycle, a missing DAG call, empty tags, catchup on, a missing owner, one task with owner `"airflow"`, low retries both DAG-wide and on one task, a swapped pipeline order, and a skipped validate step. Every file was restored exactly afterwards.

**Not covered:** these tests check how the DAGs are defined, not whether they run. They don't run any task or check the data or output files, since you asked for loading, policy and order checks only. I only ran the suite on Airflow 3.3.2, the version in `requirements.txt` and in this venv.