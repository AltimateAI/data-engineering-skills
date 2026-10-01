The repo now imports and runs on Airflow 3.3.2, and `daily_revenue` writes the same reports as before. I couldn't compare against a real 2.11 run. The only old-vs-new comparison I could run (a 3.x emulation of 2.x scheduling) failed on the old code's removed template keys. So I checked the new outputs by hand instead.

**The main risk:** on Airflow 3, a bare `"15 4 * * *"` schedule shifts every report by one day. The run would be dated the day it fires, not the previous day. I switched to `CronDataIntervalTimetable("15 4 * * *", timezone="UTC")`, which keeps the 2.x dates. The checker shows the same run dates and intervals as before, and `catchup=False` is unchanged.

**`daily_revenue`**
- **Template keys:** `execution_date` and `next_ds` no longer exist in 3.x. The SQL window now uses `ds` and `data_interval_end`. The manifest's `logical_ts` is written with `.isoformat()` so it keeps the 2.x format (`2026-03-02T04:15:00+00:00`).
- **Manual triggers:** a run with no date would have crashed on 3.x. It now falls back to the trigger date, which is what 2.x used. Your README only documents scheduled runs, so confirm you want manual runs to behave this way.
- **Renames:** I renamed the Python functions behind the two tasks (`run_daily_revenue`, `build_regions`) because the linter wants each task variable named like its `task_id`. Task ids, dependencies and output paths are unchanged.

**`region_reference`**
- `days_ago` is gone, so `start_date` is now a fixed `2026-01-01 UTC`. `DummyOperator` became `EmptyOperator`.
- It runs on manual trigger only, as before.

**Other changes**
- **Imports:** operators now come from `airflow.providers.standard`, and `DAG` from `airflow.sdk`.
- **`requirements.txt`:** pins `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.
- **Tests:** `tests/test_dag_integrity.py` uses the 3.x `DagBag` and `dagbag.dags`. A new `tests/conftest.py` turns off example DAGs. The tests still fail if a DAG doesn't import.

**What I checked**
- **Checker and lint:** the Airflow checker exits 0 with no errors, and ruff `AIR` is clean. Its one warning flags the manual-run date fallback in `daily_revenue`, which is intentional.
- **Pytest:** 2 passed.
- **Replay:** 3 consecutive scheduled `daily_revenue` runs and a manual `region_reference` trigger all succeeded. The new run dates match the previous version's preview.
- **Report content:** the 2026-03-02 CSV matches a direct DuckDB query of `orders.csv`: APAC 5 / 787.94, EMEA 2 / 207.25, NA 1 / 7.32.

**Not verified**
- **Real 2.11 outputs:** there is no 2.x environment here.
- **Report files:** for `daily_revenue`, a byte-for-byte diff of the CSV against 2.11 output.
- **Deployment config:** check whether your old deployment overrode `catchup_by_default` or the cron/delta interval settings. I assumed the 2.x defaults, which doesn't matter for `daily_revenue` because it sets `catchup=False` explicitly.

Nothing is committed.