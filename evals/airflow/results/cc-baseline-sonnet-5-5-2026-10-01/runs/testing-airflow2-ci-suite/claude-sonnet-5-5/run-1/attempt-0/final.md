I added the suite in `tests/` (`conftest.py` and `test_dags.py`). `pytest tests/` passes in this venv with 14 tests, and I didn't touch the DAGs. I didn't try breaking a DAG to confirm each test fails when it should.

- **Imports:** each file in `dags/` is imported on its own, and the DagBag is checked for import errors. A broken DAG file fails under its own file name.
- **Schedule:** `shipments_daily` must be `30 7 * * 1-5` in UTC. The test also walks the next 10 firings and checks each is 07:30 on a weekday.
- **Retries:** every task in every DAG needs `retries >= 2`.
- **Dependency:** `build_report` must be downstream of `extract_shipments`.
- **Late rules:** six tests on `find_late_shipments`, each isolating one rule from your description:
  - delivered on the run date after the promise
  - delivered on time
  - delivered on another day
  - undelivered and overdue, counted to the run date
  - undelivered but not yet due
  - sort order
- **End to end:** runs `shipments_daily` for 2026-03-03 with `dag.test()` on `data/shipments.csv` and checks the DAG run succeeds. The report must list SH-1009 (5 days), SH-1003 (3), SH-1007 (2) and SH-1001 (1), in that order. I checked those figures by hand against your rules.

The tests set `AIRFLOW_HOME` and the metadata DB to a temporary directory before Airflow loads. They need no scheduler or webserver and never touch a real Airflow install. The end-to-end test writes its report to a temp directory, so the repo's `output/` stays untouched.

`requirements.txt` only lists Airflow, so CI needs `pytest` installed. It's already in this venv. I didn't edit the requirements file; say if you want a dev requirements entry.

One thing I noticed: `find_late_shipments` also skips any shipment whose `ship_date` is after the run date. Your rules don't mention that, and no test covers it.