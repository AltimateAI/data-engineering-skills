I added `dags/vendor_shipments.py`. It compiles, but Airflow isn't installed here, so I haven't run the DAG, and the sensor and the DuckDB load are untested.

- **Schedule:** I used `CronTriggerTimetable("0 6 * * *", "UTC")` instead of a bare cron string. With it, the run at 06:00 on day D has `ds` = D and picks up `shipments_D.csv`. A plain cron string can behave differently depending on the `create_cron_data_intervals` setting.
- **Backfill:** `start_date` is 2026-09-01 and `catchup=False`. Nothing backfills on deploy, but you can trigger or clear any day since 2026-09-01 by hand.
- **Wait:** `wait_for_file` is a `FileSensor` on `{{ var.value.vendor_landing_dir }}/shipments_{{ ds }}.csv`. It runs in `reschedule` mode, so it frees its worker slot between 5-minute checks. The timeout is 18 hours, which is 06:00 to midnight UTC. If the file isn't there by then, the task fails and the run fails. Its `retries` is 0, because the default 2 retries would restart the wait.
- **Load:** `load_shipments` creates `vendor_shipments` if needed, using the columns from the sample file plus `ship_date`. The delete of that day's rows and the insert happen in one transaction, so a rerun replaces the day's rows instead of duplicating them. It reads the file path from the Variable.
- **Publish:** `publish_report` runs `scripts/publish_shipments_report.sh {{ ds }}`.

The `vendor_landing_dir` Variable has to exist in each environment before the first run.