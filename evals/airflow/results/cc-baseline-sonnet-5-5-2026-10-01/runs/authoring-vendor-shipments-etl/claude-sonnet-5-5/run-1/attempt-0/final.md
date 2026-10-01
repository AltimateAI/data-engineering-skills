I added `dags/vendor_shipments.py`, and a local `airflow dags test vendor_shipments 2026-09-28` ran all three tasks to success. I didn't test the late-file timeout, a rerun of the same day, or a missing-file failure.

For the local test I set `vendor_landing_dir` to `data/incoming` and created the `fs_default` connection with an environment variable. The report came out with 4 carriers. I deleted the test warehouse, report and Airflow home afterwards.

- **Schedule:** it runs at `0 6 * * *` UTC. The start date is 2026-09-01 and `catchup=False`, so deploying it won't backfill. You can still trigger or clear any day since 09-01 by hand. `max_active_runs=1` keeps reruns from fighting over DuckDB's single-writer lock.
- **Waiting for the file:** `wait_for_file` is a `FileSensor` on `{{ var.value.vendor_landing_dir }}/shipments_{{ ds }}.csv`. It uses `mode="reschedule"`, so it frees its worker slot between 10-minute checks.
- **Timeout:** it gives up after 18 hours, which is the end of the day for a 06:00 run, and then fails the run. It has `retries=0` because a retry would restart the wait and run past midnight. The other tasks keep the existing DAG's 2 retries.
- **Load:** `load_shipments` creates `vendor_shipments` if needed, with the CSV's five columns plus `ship_date`. It deletes that date's rows and inserts the file inside one transaction, so a rerun replaces the day's rows and a failed load rolls back.
- **Report:** `publish_shipments_report` runs `scripts/publish_shipments_report.sh {{ ds }}`.

The `FileSensor` needs an Airflow connection named `fs_default`, and I couldn't check whether your environments have one. Without it, the sensor fails with an error on its first check. If you'd rather not depend on the connection, I can switch to a `PythonSensor`.

I didn't commit anything.