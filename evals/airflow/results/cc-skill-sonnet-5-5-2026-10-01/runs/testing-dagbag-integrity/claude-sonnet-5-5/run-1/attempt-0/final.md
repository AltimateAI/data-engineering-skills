I added the suite in `tests/`. `pytest tests/` passes on the current code: 12 tests in about 1.6 s on Airflow 3.3.2. It needs only the venv, because it uses a throwaway sqlite DB and doesn't touch a scheduler or webserver. I didn't change anything in `dags/`; `git status` shows only the new `tests/` directory.

- **Files:** `tests/conftest.py` sets up the temporary Airflow environment and the DAG parsing. `tests/test_dags.py` holds the tests.

**Rules covered**
- **Every file in `dags/` loads:** `test_no_import_errors` fails if any DAG file fails to import, and it prints the traceback. `test_expected_dags_present` fails if a DAG silently stops being defined. `test_dags_are_acyclic` runs `dag.validate()` on every DAG.
- **At least one tag:** `test_every_dag_has_a_tag`.
- **Catchup off:** `test_catchup_disabled`.
- **Real owner:** `test_tasks_have_real_owner` checks every task and fails if the owner is empty or "airflow".
- **At least 2 retries:** `test_tasks_have_min_retries` checks every task. The test reads each task, not the DAG defaults, so a task-level override is caught.
- **`orders_ingest` order:** `test_orders_ingest_task_set` and `test_orders_ingest_edges` check the exact upstream and downstream tasks of each step. That covers `extract_orders -> validate_orders -> load_orders -> publish_summary` and rules out extra or reversed edges.

**Mutation check:** I planted a bug for each rule and ran the suite against it. All were caught by the intended test:
- a dropped tag
- `catchup=True`
- owner set to "airflow"
- `retries` set to 1 on `customer_snapshot` and to 0 on `marketing_spend`'s `fetch_spend` override
- a bad import
- a dependency cycle
- a removed or swapped step in `orders_ingest`

One mutation I tried survived, but it wasn't tied to any of your rules, so I didn't add a test for it.

**Things to know**
- `EXPECTED_DAG_IDS` in `tests/test_dags.py` lists the three current DAGs. When you add a DAG, add its id there; the tag, catchup, owner and retries checks cover new DAGs automatically.
- The suite doesn't run any tasks or check schedules. You didn't ask for either, so I left them out.