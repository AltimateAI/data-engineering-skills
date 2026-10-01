I added `dags/vendor_shipments.py`. The three-run test passed: a scheduled run for 2026-09-28, a manual run, and a rerun. That test only covered a file that was already present. I never watched the sensor wait on a missing file or hit its 18-hour timeout.

- **Schedule:** `0 6 * * *` UTC, `start_date` 2026-09-01, `catchup=False`. Deploying won't backfill, and you can still rerun any day since 09-01 by hand.
- **Which day a run processes:** the run's own UTC day. A scheduled run uses its logical date. A manual trigger with no date uses its trigger date, because Airflow 3 manual runs have no `{{ ds }}`. The existing `warehouse_orders` DAG uses `{{ ds }}`, so it would fail on a no-date manual trigger. I left it alone.
- **Waiting:** `wait_for_file` checks for `<vendor_landing_dir>/shipments_<day>.csv` every 10 minutes. It runs in `reschedule` mode, so it doesn't hold a worker slot between checks. It times out after 18 hours, which is the end of the UTC day for a 06:00 run. A timeout fails the run without retries, so on-call gets paged. It reads the Variable inside the task, not at parse time.
- **Loading:** the `load_shipments` task creates `vendor_shipments` if it doesn't exist. In one transaction it deletes that day's `ship_date` rows and inserts the file's rows with `ship_date` set. Reruns don't duplicate. The table has `shipment_id`, `carrier`, `destination`, `weight_kg`, `shipped_at` and `ship_date`, taken from the header of the sample file.
- **Report:** `publish_shipments_report` is a `BashOperator` that runs `scripts/publish_shipments_report.sh <day>` by absolute path.

Verification:
- The Airflow check passed with exit 0 and no import errors. Its one warning says the date comes from the run time, which is what I intended.
- I ran it against `data/incoming` on Airflow 3.3.2. All three runs succeeded, the warehouse held 25 rows for 2026-09-28 with 25 distinct IDs, and `reports/shipments_2026-09-28.csv` was written. That run created `warehouse/analytics.duckdb` and `reports/` locally. `git status` shows only the new DAG file.
- I never ran a real warehouse or an actual late-arriving file.

On-call alerting depends on your failure callbacks or alerting setup, which I didn't change.