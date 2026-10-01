The suite is in `tests/` and `pytest tests/` passes (20 tests, about 1 second) in this venv. The DAGs are untouched. I only ran it against the current code. I didn't break a DAG on purpose to confirm each test fails when it should.

**What's covered**
- **Imports:** there's one test per file in `dags/`, plus a check that the DagBag has no import errors and that every file defines a DAG.
- **Schedule:** `shipments_daily` must use UTC. Over four weeks, every run falls at 07:30 on a weekday, and every weekday gets exactly one run.
- **Retries:** every task in every DAG must have `retries >= 2`.
- **Dependency:** `build_report` must be downstream of `extract_shipments`.
- **Late rules:** 10 parametrized cases cover each branch of your rules, including the boundaries. They check that `days_late` counts to delivery or to the run date, and that results sort worst first. There's no case for a shipment that was not yet shipped on the run date, because your rules don't mention one.
- **End to end:** the test runs the DAG's tasks in dependency order on `data/` for 2026-03-03. It expects SH-1009 (5 days late), SH-1003 (3), SH-1007 (2) and SH-1001 (1).

**Test setup**
- **No Airflow database:** the tests never touch an Airflow metadata DB. They read DAGs from `dagbag.dags[...]` instead of `get_dag()`, which queries the database and fails on a fresh CI box.
- **Not `airflow dags test`:** the end-to-end test calls each task's Python function in order, with the XCom handed over in memory. That avoids needing `airflow db init` in CI, but it isn't the same as running `airflow dags test`.
- **Output location:** the end-to-end test writes its CSV to `tmp_path`, so nothing lands in the repo's `output/` directory.

The files are `tests/conftest.py`, `tests/test_dags.py` and `tests/test_shipments_daily.py`. Nothing is committed yet.