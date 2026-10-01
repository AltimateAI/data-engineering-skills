I've added a pytest suite in `tests/`. `pytest tests/ -q` gives **21 passed in about 3 s** on Airflow 2.11.2, which is the version in `requirements.txt` and in the venv. The DAG files are unchanged, and the end-to-end run writes nothing into the repo's `output/` folder.

**How it runs in CI:** `tests/conftest.py` sets up a throwaway Airflow home and sqlite database in a temp directory before Airflow is imported. So CI needs no scheduler, no webserver, no `airflow.cfg` and no connections, and it never touches anyone's local Airflow database.

**How each requirement is tested:**

| Requirement | Test |
|---|---|
| Every DAG file imports | `test_dag_integrity.py`: no import errors, both DAG ids are present, and every file in `dags/` defines a DAG (so a file that imports but stops defining its DAG still fails) |
| shipments_daily at 07:30 UTC, Mon–Fri only | `test_runs_at_0730_utc_weekdays_only`: asks Airflow's own scheduling logic for the next 10 runs and checks the weekdays, the 07:30 time and the UTC offset |
| Every task has at least 2 retries | `test_every_task_has_at_least_two_retries`: checks each task's own setting, so a single task overriding the default is also caught |
| Report only after the export is extracted | `test_report_is_built_only_after_extract` |
| Late-shipment rules and `days_late` | `test_late_shipment_rules.py`: small hand-built cases for each part of the rule and its edges (delivered on the promised day, delivered on another day, still open and due today, crossing the end of February) |
| End-to-end run on `data/` for 2026-03-03 | `test_shipments_daily_end_to_end`: runs the whole DAG and checks every task succeeded. It then checks the exact report: SH-1009 (5 days), SH-1003 (3), SH-1007 (2), SH-1001 (1), which I worked out by hand from `data/shipments.csv` |

**Proof the tests catch bugs:** I planted 19 small bugs in the DAGs one at a time, ran the suite each time, and restored the files afterwards. All 19 were caught by a specific failing test. They included:
- a broken import in each DAG file
- Saturday added to the schedule, the time moved to 07:00, a daily schedule, and a Berlin timezone
- retries lowered to 1 on each DAG, and one task overridden to 0
- the report task running alongside or before the extract
- off-by-one errors in each late-shipment comparison and in `days_late`
- a wrong start date for `days_late`, a wrong sort order, and a renamed DAG

**Things you should know:**
- **The code has one condition your rules don't mention.** `find_late_shipments` skips any shipment whose `ship_date` is after the run date. With normal data this never matters, so I didn't test it either way.
- **Report order:** the report is sorted worst-first (most days late first, then by shipment id). The end-to-end test checks this order because the current code defines it.
- **Run date vs. when the run starts:** in Airflow 2, the run for date 2026-03-03 actually starts at 07:30 on 03-04, and Friday's run starts Monday morning. The schedule test checks the real start times (weekdays at 07:30 UTC). The late-shipment logic uses the run date (`ds`), as your rules describe.
- **Not covered:** behaviour under a real scheduler and other Airflow versions. `carrier_rates_weekly` is only covered by the import and retry checks, since you didn't list any rules for its logic.

Nothing is committed; `tests/` is untracked and ready for you to review.