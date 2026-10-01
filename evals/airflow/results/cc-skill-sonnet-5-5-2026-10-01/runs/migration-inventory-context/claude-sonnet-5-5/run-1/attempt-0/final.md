`inventory_snapshot` now runs on Airflow 3.3.2, and I expect the snapshot CSVs and audit JSON to come out as before. I ran two days and confirmed the files are produced with the right dates and the change column. I didn't diff them against output from the old 2.x code, because there was no 2.x environment to produce it. Nothing is committed.

**What changed**
- **Schedule:** the daily `timedelta` is now `DeltaDataIntervalTimetable(timedelta(days=1))`. A plain `timedelta` on 3.x would fire at the end of the day and shift every output date by one day. The preview of scheduled run dates and intervals matches the 2.x behaviour.
- **Catchup:** `catchup=False` is unchanged.
- **Date handling:** `execution_date` is now `logical_date`, and `prev_ds`, which no longer exists, is computed as `logical_date - 1 day`. Snapshot file names, the audit `day` field, the end-of-day cutoff and the change column all use the same dates as before.
- **XCom:** the audit task now pulls from `build_snapshot` explicitly. On 3.x a pull without a task id returns `None`, so the audit's `sku_count` and `low_stock` would have come out null.
- **Imports:** `PythonOperator` now comes from the standard provider, `DAG` from `airflow.sdk`, and `provide_context` is gone.
- **`requirements.txt`:** pinned `apache-airflow==3.3.2` and added `apache-airflow-providers-standard==1.19.0`, the installed version.

**What I checked**
- **Parse check:** it reports 0 errors.
- **Run preview:** it matches the 2.x baseline for logical date, data interval and catchup.
- **Test runs:** `airflow dags test` succeeded for the 2026-02-21 and 2026-02-22 runs. The 02-22 file showed the right changes against 02-21, and the audit JSONs had the right day, SKU count and low-stock list.

**What I didn't check or left alone**
- **No 2.x environment:** I captured the baseline by switching the 3.x scheduler back to its 2.x defaults, and the repo has no pre-existing tests.
- **Manual runs:** a run triggered by hand with no logical date would fail in `build_snapshot`. The README only describes scheduled runs, so I left that alone. The checker flags it as a warning.
- **`ruff` AIR001:** it wants the task variables named after their task ids. That's cosmetic, so I left it.

I removed the `output/` files from the test runs. They were git-ignored anyway.