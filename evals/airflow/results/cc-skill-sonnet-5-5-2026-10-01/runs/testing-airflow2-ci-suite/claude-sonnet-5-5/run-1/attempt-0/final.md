The suite is in `tests/` (`conftest.py` and `test_dags.py`), and `python -m pytest tests/ -q` gives 12 passed in about 3 seconds on Airflow 2.11.2. Run it with the venv's Python: the bare `pytest` on this machine's PATH isn't the venv's and fails with `No module named 'airflow'`. The suite uses a throwaway sqlite DB and a temp `AIRFLOW_HOME`, so it needs no scheduler, webserver or connections. I didn't edit the DAGs, and `git status` shows only the new `tests/` folder.

| Rule | Test |
|---|---|
| Every DAG file imports | `test_no_import_errors`, plus `test_expected_dags_load` so a DAG can't silently disappear |
| `shipments_daily` runs 07:30 UTC, Mon–Fri only | `test_shipments_daily_runs_0730_utc_weekdays` generates 10 real runs from the timetable and checks the weekdays, the time and a zero UTC offset |
| Every task has at least 2 retries | `test_every_task_has_at_least_two_retries` checks each task in every DAG, so a task-level override is caught |
| Report is built only after the export | `test_report_built_only_after_extract` checks that `extract_shipments` is upstream of `build_report` |
| Late-shipment rules | Six unit tests on `find_late_shipments` cover delivered late on the run date, on time or early, delivered late on another day, open and overdue, open but promised on or after the run date, and the ordering of results |
| End to end for 2026-03-03 | `test_shipments_daily_end_to_end_on_sample_data` runs the DAG with `dag.test()` and asserts the run succeeded. It checks that SH-1001, SH-1003, SH-1007 and SH-1009 are in the report, that the five non-late shipments are absent, and that SH-1001 is 1 day late and SH-1009 is 5. It also checks that every row satisfies the rule. |

The end-to-end test writes its output to `tmp_path`, so it doesn't create `output/` in the repo.

**Mutation check:** I planted 10 bugs, one per rule. They were a wrong weekday set, a wrong hour, retries below 2, a broken dependency edge, and the three late-shipment comparisons (the delivery-day filter, "delivered on or before promised", and "promised on or after run date"). The last two were an off-by-one in `days_late` and removing the retries setting from `carrier_rates_weekly`. Nine were caught. The survivor was removing the `ship_date > as_of` guard in `find_late_shipments`. That guard isn't in your rules and doesn't change the sample data, so I didn't add a test that would lock it in. If you want it kept, say so and I'll add a test.

**Behaviour to know about:** `shipments_daily` uses a cron data interval, which is Airflow 2.x behaviour. A scheduled run fires at 07:30 on its tick, but `ds` is the previous tick's date. So Monday's scheduled run reports for Friday, and Tuesday's reports for Monday. The tests don't assert this, because you didn't specify which date a scheduled run should report on. Your 2026-03-03 test passes that date in explicitly.

**Not verified:** behaviour under a real scheduler, real connections, or any Airflow version other than 2.11.2.