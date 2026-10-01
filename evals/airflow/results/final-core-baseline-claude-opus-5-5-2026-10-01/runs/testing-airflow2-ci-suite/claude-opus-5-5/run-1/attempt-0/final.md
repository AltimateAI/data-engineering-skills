The suite is in `tests/`. `pytest tests/` passes on the current code (20 tests, about 2 seconds), and the DAGs are the same as HEAD. Nothing is committed yet.

**What it covers**
- **DAG files import:** each `.py` file in `dags/`, including subfolders, is loaded on its own and must load with no errors. It loads every file, including ones that don't mention "airflow" or "dag", which Airflow's default loader would silently skip.
- **Schedule:** generates two weeks of `shipments_daily` run times and checks they are exactly Monday to Friday at 07:30 UTC. This catches a wrong cron, a wrong hour or a non-UTC timezone.
- **Retries:** every task in every DAG must have at least 2 retries, including tasks that override the DAG default.
- **Report after extract:** `extract_shipments` must come before `build_report`, and every task on the path between them must wait for its upstream tasks to succeed. So the report can't run after a failed extract.
- **Late-shipment rules:** one case per rule and each boundary (delivered today late, on time or early; delivered late on an earlier day; open with a promised date before, on or after the run date; `days_late` across a month end), plus a mixed batch.
- **End to end:** runs `shipments_daily` for 2026-03-03 on `data/` with `dag.test()`. It checks every task succeeded and the CSV contains exactly SH-1009 (5), SH-1003 (3), SH-1007 (2) and SH-1001 (1). The expected rows are worked out by hand, not by calling the DAG's own function.

**How it runs in CI:** `tests/conftest.py` points Airflow at a temporary home directory with its own SQLite database before Airflow is first imported. It never reads or touches CI's or anyone's `~/airflow`. Only the end-to-end test sets up the database. That test also writes the report to a temp folder, so it doesn't leave `output/` behind and can't pass on an old file.

**Checking the tests catch problems:** I broke a copy of the repo one way at a time: an import error, a new broken file, weekend or wrong-hour cron, a non-UTC timezone, retries of 1 or 0, report running alongside extract, an `all_done` trigger rule, and four different errors in the late rules. The suite failed for every one.

**A mistake during that check:** my first attempt couldn't create a temp folder in the sandbox and applied the breakages to your real `dags/` files instead. I spotted it from `git status`, restored both files from HEAD and deleted the stray `dags/helper.py` it had created. `git diff HEAD` is now clean, and I redid the check on a copy outside the repo.

**Behaviour your rules don't define, which I left untested**
- `find_late_shipments` skips shipments whose `ship_date` is after the run date. Your rules don't mention this. It only matters for an open shipment that hasn't shipped yet but is already past its promised date.
- When re-running an old date (a backfill), a shipment delivered after that date is treated as neither late-delivered nor still open, so it isn't reported. Your rules could be read either way.
- `start_date` has no timezone, so the 07:30 is only UTC because Airflow's default timezone is UTC. The tests pin that default, so if production sets a different `default_timezone`, the schedule would move and this suite wouldn't notice. Giving `start_date` an explicit UTC timezone would close that gap, but that's a DAG change, so I left it.