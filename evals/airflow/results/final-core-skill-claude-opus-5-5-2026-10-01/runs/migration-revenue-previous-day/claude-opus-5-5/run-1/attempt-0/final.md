The repo is migrated to Airflow 3.3.2. I replayed `daily_revenue` on a real Airflow 2.11 environment and on 3.3.2, and its reports came out byte-for-byte identical. Nothing is committed yet.

## What changed

**`daily_revenue`**
- **Schedule:** on Airflow 3, the bare cron string `"15 4 * * *"` would quietly change what each run processes. The 04:15 run on 03-05 would report 03-05 (a day still in progress) instead of 03-04, so every report would shift by a day. I made the schedule explicit with `CronDataIntervalTimetable("15 4 * * *", timezone="UTC")`, so each run still covers the UTC day that just closed. I kept `catchup=False` and `max_active_runs=1`.
- **Removed template variables:** Airflow 3 dropped `next_ds` (used in `sql/daily_revenue.sql`) and `execution_date` (used in the manifest). I replaced them with small helpers, `business_date`, `business_end_date` and `logical_ts`, available inside the templates. The CSV and manifest file names, columns and formats are unchanged; the manifest's `logical_ts` value is still the same string.
- **Imports** now use the `airflow.sdk` and standard-provider paths.
- **Function names:** I renamed the Python functions behind the tasks so the task variables can match the task ids (a ruff Airflow rule). Task ids and dependencies are unchanged.

**`region_reference`:** updated imports, replaced `DummyOperator` with `EmptyOperator`, and replaced `days_ago(1)` (removed in Airflow 3) with a fixed start date of 2026-01-01. It's manual-only, so this has no effect.

**`requirements.txt`:** now pins `apache-airflow==3.3.2` and adds `apache-airflow-providers-standard==1.19.0`.

**`tests/test_dag_integrity.py`:** moved to the Airflow 3 `DagBag` API. I added checks that the schedule is the 04:15 UTC "previous day" one and that a manual run picks the right day. I also confirmed the suite still fails when a DAG file doesn't import.

## Verification
- **Replay:** I ran 5 consecutive scheduled `daily_revenue` runs (reports for 2026-03-02 to 03-06) on both versions. The run dates match and all 10 output files (5 CSVs, 5 manifests) are identical.
- **`region_reference`:** a manual trigger gave an identical `regions.csv` on both versions. My first replay showed a difference only because I picked a trigger date before the old `days_ago` start date.
- **Checks:** the migration checker finds no problems, the ruff Airflow rules pass, the schedule preview matches 2.x, and pytest passes 4 of 4.

## Decision for you: manual triggers of `daily_revenue`
The README only lists this DAG as scheduled, but someone can still trigger it by hand:
- **On 2.11:** a manual trigger wrote an **empty** report named for the trigger day, because the query's start and end dates came out equal.
- **On 3.3 unchanged:** a manual trigger would just fail.
- **What I did:** a manual trigger now re-runs the most recent closed business day. Triggering at 03-06 09:15 rewrites `2026-03-05.csv` with the same rows the scheduled run produced. Only that manifest's `logical_ts` differs, showing the trigger time.

This is the one deliberate change from 2.x behaviour, and scheduled reports are unaffected. If you'd rather manual triggers fail or behave some other way, tell me and I'll change it.

## Also worth knowing
- The local virtualenv has newer duckdb (1.5.6) and pytest (9.1.1) than `requirements.txt` pins (1.4.4 and 8.4.2). My checks ran on the newer versions, so make sure your 3.3 image installs what you expect.
- The README's `airflow dags test daily_revenue 2026-03-04` still works on 3.3. It builds the report for the day before the date you give it (03-03 here), the same as on 2.11.