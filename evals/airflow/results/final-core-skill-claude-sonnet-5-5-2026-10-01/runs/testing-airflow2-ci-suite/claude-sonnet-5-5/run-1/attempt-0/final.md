I added the pytest suite in `tests/`. `pytest tests/ -q` gives 16 passed in about 3 s in this venv (Airflow 2.11.2). I didn't change anything in `dags/`, and `git status` shows only the new `tests/` directory.

| Rule | Test |
|---|---|
| Every DAG file imports (and both expected DAGs exist) | `test_structure.py::test_no_import_errors`, `test_expected_dags_load` |
| `shipments_daily` runs 07:30 UTC, Monday to Friday only | `test_schedule.py::test_shipments_daily_weekdays_0730_utc` |
| Every task in every DAG has at least 2 retries | `test_structure.py::test_every_task_has_at_least_two_retries` |
| The report is built only after the export is extracted | `test_structure.py::test_shipments_report_runs_after_extract` |
| Late-shipment rules and `days_late` | `test_shipments_rules.py` (10 cases, hand-built inputs) |
| End to end on the sample data for 2026-03-03 | `test_shipments_e2e.py` |

The schedule test generates the next 15 runs from the DAG's own timetable. It asserts the weekday set, the time and the UTC offset, rather than comparing the cron string.

The late-shipment tests cover each branch and each boundary. That includes delivered on the promised date, delivered on another day, undelivered promised today, a month boundary, and the sort order.

The end-to-end test checks that the run succeeded and that the 2026-03-03 report lists SH-1009 (5 days), SH-1003 (3), SH-1007 (2) and SH-1001 (1), in that order. I worked those out by hand from `data/shipments.csv`. The test redirects output to a temp directory, so the repo's `output/` stays clean.

To check the tests actually catch bugs, I planted 12 bugs, one at a time, and restored the files afterwards. The bugs were a wrong weekday, a wrong hour, Saturday added, retries lowered in each DAG, the dependency edge removed, an off-by-one on each late-shipment comparison, a wrong `days_late` calculation, and an import break. The suite failed on all 12. The import break was caught as a collection error rather than by a named test, which still turns CI red.

- **`ship_date` rule:** `find_late_shipments` skips shipments whose `ship_date` is after the run date. You didn't state that rule, so I left it out of the tests, but SH-1006 in the sample data depends on it.
- **Run dates:** On 2.11 each run's date (`ds`) is the previous schedule slot, so the Monday 07:30 run reports on Friday. The tests don't assert this.
- **Not verified:** I only ran this on Airflow 2.11, with no scheduler and no real connections. Because Airflow is pinned to 2.11, the tests use `execution_date=` and won't work unchanged on Airflow 3.