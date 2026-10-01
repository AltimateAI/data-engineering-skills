The repo is migrated to Airflow 3.3, and `daily_revenue` produces the same reports as before. Its revenue CSVs for Mar 2–7 are byte-identical to the 2.11 version, and the manifest's format matches too. The tests pass (3 of 3) and both DAGs run successfully under `airflow dags test`. Nothing is committed yet.

**The change that matters most: which day gets reported.** On 3.x, a plain cron string like `"15 4 * * *"` gets different scheduling by default. Today, the 04:15 run on Mar 5 reports Mar 4. On 3.3 that same run would report Mar 5, the day that has only just started, so finance would have gotten the wrong, incomplete day with no error raised. I checked this directly: the 3.x default gives the Mar 5 run a date of Mar 5. I fixed it by declaring the old scheduling behaviour explicitly (`CronDataIntervalTimetable("15 4 * * *", timezone="UTC")`) and added a test that fails if it ever reverts.

**Other changes:**
- **Removed date variables:**
  - In `daily_revenue.sql`, `{{ next_ds }}` (no longer available) is replaced with `{{ macros.ds_add(ds, 1) }}`, which gives the same value.
  - In the manifest, `{{ execution_date }}` (also gone) is replaced with `{{ ts }}`. I first tried `{{ logical_date }}`, but it writes `2026-03-04 00:00:00+00:00`. `{{ ts }}` keeps the old `2026-03-04T00:00:00+00:00`, so the dashboard reading the manifest sees no change.
- **Imports and settings:** `DAG` now comes from `airflow.sdk` and the operators from the standard provider package. `schedule_interval=` becomes `schedule=` and `DummyOperator` becomes `EmptyOperator`. `days_ago(1)`, which no longer exists, is replaced with a fixed start date in `region_reference`.
- **Tests:** `DagBag` no longer accepts `include_examples`, and `get_dag()` now needs a database, so the tests read `dagbag.dags` and still run without one.
- **`requirements.txt`:** pinned `apache-airflow==3.3.2` and added `apache-airflow-providers-standard==1.19.0`.

**How I verified it:** before editing, I saved the reports the old code produces for Mar 1–8. I then ran `airflow dags test daily_revenue <date>` on 3.3.2 for Mar 2–7 and compared each CSV to the saved copy. I deleted the temporary files and generated output afterwards.

**Worth knowing:**
- **Pins:** your local environment has duckdb 1.5.6 and pytest 9.1.1, but `requirements.txt` still pins 1.4.4 and 8.4.2. I tested against the installed versions. I left the pins alone; say if you want them aligned.
- **Manual runs:** if someone triggers `daily_revenue` from the 3.x UI, the "logical date" they enter becomes the business date that gets reported. That's the same as on 2.11, but 3.x fills that field with the current time by default. Anyone rerunning a day should set it to the day they want.