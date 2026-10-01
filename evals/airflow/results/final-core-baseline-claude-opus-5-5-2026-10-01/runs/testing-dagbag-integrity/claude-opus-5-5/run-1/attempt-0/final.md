I've added a test suite under `tests/`. `pytest tests/` passes on the current code (11 tests, about 2 seconds). I then broke the DAGs one way at a time, and the suite failed on every break, naming the right file, DAG or task. The DAGs are back to their original state and I haven't committed anything.

**What's in it**
- **`tests/conftest.py`**: points `AIRFLOW_HOME` at a temporary folder and turns off example DAGs, so CI doesn't need a database or any Airflow services. It loads `dags/` once with `safe_mode=False`. Normally Airflow skips files that don't contain the words "dag" and "airflow"; this setting makes it parse every file.
- **`tests/test_dag_integrity.py`**:
  - fails if any file has an import error. Cycles and other DAG validation errors show up as import errors too.
  - checks that every `.py` file in `dags/` actually defines at least one DAG. This catches a file that imports cleanly but defines nothing, such as a `@dag` function that is never called. That is the "vanished from the UI" case.
  - checks that each DAG can be converted into the form Airflow stores DAGs in (serialized). A DAG that imports fine but can't be serialized also never reaches the UI.
- **`tests/test_dag_policy.py`**: every DAG needs at least one tag and catchup off. Every task needs an owner that isn't empty or `"airflow"`, and at least 2 retries. All violations are listed together, e.g. `marketing_spend: task 'fetch_spend' has no real owner (owner='airflow')`.
- **`tests/test_orders_ingest.py`**: `orders_ingest` must have exactly the four tasks wired as `extract_orders -> validate_orders -> load_orders -> publish_summary`, with no other connections.

**Breaks the suite caught**
- an import of a missing module
- a dependency cycle
- a `@dag` function that is never called
- a new `.py` file in `dags/` with no DAG in it
- catchup turned on
- tags removed
- owner falling back to `airflow`
- `retries=1`
- `validate_orders` and `load_orders` swapped in `orders_ingest`

**Decision for you:** the `orders_ingest` test fails if anyone adds a fifth task to that DAG, even one that leaves the four-step order intact. I read your requirement as "the pipeline is exactly these steps." The catch is that someone would have to update the test to add, say, an alerting task. If you'd rather only check that these four run in this order, I can loosen it.