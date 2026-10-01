I've added a pytest suite under `tests/` for orders_enrichment. `pytest tests/` gives **28 passed in about 8 s** on Airflow 3.3.2 in the CI venv. I didn't change the DAG (`git diff` is empty; only `tests/` is new), and the runs write nothing to the repo's `output/`.

**Files**
- `tests/conftest.py`: sets up Airflow before import (a temporary sqlite metadata DB that is thrown away, `dags/` as the DAGs folder) and provides the shared fixtures.
- `tests/test_transforms.py`: calls each task function directly on small hand-built rows.
- `tests/test_dag_structure.py`: checks the DAG imports, the task wiring and the schedule.
- `tests/test_end_to_end.py`: full in-process runs with `dag.test()`, which needs no scheduler or webserver. Output is sent to a temp directory, not `output/`.

**How each rule is covered**
- **Latest version kept:** unit tests include an older version exported after the latest one, the latest arriving first, and versions only minutes apart. The end-to-end run on 2026-03-02 shows S-102 kept at 120.00 (not 100.00) and S-103 at 40.50 (not 38.00).
- **amount × that day's rate, rounded half-up to cents:** cases like 0.625 → 0.63 and 0.125 → 0.13, which plain banker's rounding would get wrong. Another test checks that rates from other days are ignored. The end-to-end run checks the whole output file against values I worked out by hand: 130.20, 51.44, 9.99, 0.38.
- **Missing FX rate fails the run:** a unit test checks that conversion raises an error. An end-to-end run with a JPY order whose only rate is from the previous day must fail at `convert_to_usd` and write no file.
- **Nothing written unless validate_totals passed:** the write task's only upstream task is `validate_totals`, and it only runs if everything before it succeeded. An end-to-end run with an order that has no customer must fail at `validate_totals` and write no file.
- **Daily at 06:00 UTC:** I generate 14 upcoming runs from the DAG's real schedule and check each is at 06:00:00 UTC, on 14 consecutive days. The run that fires on a day also processes that day's data.

**Checking the tests catch bugs:** I planted 12 small bugs in the DAG, one at a time, and the suite failed on all 12. The DAG file was restored automatically after each. The bugs included:
- reversing or dropping the `updated_at` comparison;
- switching to banker's rounding, or rounding to 0.1;
- using a default rate of 1 for a missing currency;
- using the rate from any earlier day;
- removing the order-date filter;
- writing the file without waiting for validation;
- disabling validation;
- moving the schedule to 07:00, or to weekdays only.

**Things to know**
- The two failure-path tests set retries to 0 for that run only. The DAG retries failed tasks twice with a 10-minute wait, so without this they hang for about 20 minutes.
- Picking the latest version compares `updated_at` as text. That works for the sample data's timestamp format (`2026-03-02T11:47:00`). If an export ever uses a different format or adds timezone offsets, it could pick the wrong version, and these tests wouldn't notice.
- Not tested: real scheduler behaviour, and manual triggers without a date.