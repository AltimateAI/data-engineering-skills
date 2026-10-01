I added the two tests, and both fail because the DAGs don't follow the rules yet. I didn't change any DAG code. `pytest tests -q` gives 2 failed, 2 passed. The two failures are the new rule tests; the two passes are the existing placeholder test and a new DAG import check.

- **Retries:** `events_load.append_events` and `daily_revenue.aggregate` have `retries == 0`. Only `orders_pipeline` sets `default_args={"retries": 2}`.
- **Weekdays:** `orders_pipeline` uses `0 5 * * *`, which runs every day including Saturday and Sunday. A cron like `0 5 * * 1-5` would fix it.

**What I added**
- `tests/conftest.py` sets up a throwaway Airflow config and database and provides a `dagbag` fixture. It also has an `upcoming_runs` fixture that returns the next scheduled run times for a DAG.
- `tests/test_dag_rules.py` holds three tests:
  - `test_dags_import` checks that every DAG file imports and the three expected DAGs exist.
  - `test_every_task_has_2_retries` loops over every task in every DAG and reads `task.retries`, so a task-level override can't slip past it.
  - `test_orders_pipeline_runs_weekdays_only` generates the next 14 scheduled runs from a Monday and asserts the weekdays are exactly Monday to Friday.

Airflow is 3.3.2, pinned in `requirements.txt`.

I skipped the mutation check, which plants a deliberate bug to confirm each test fails, because it needs a fully green suite first. Once you fix the DAGs, I can run it.

I didn't test real connections or scheduler behaviour.

Do you want me to fix the DAGs so the tests pass?