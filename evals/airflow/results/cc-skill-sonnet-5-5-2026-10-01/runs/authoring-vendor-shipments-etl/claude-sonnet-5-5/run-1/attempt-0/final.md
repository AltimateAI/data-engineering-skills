I added the `vendor_shipments` DAG in `dags/vendor_shipments.py`, and it ran end to end on the sample file.

**Test run.** I ran `airflow dags test vendor_shipments 2026-09-28T06:00:00+00:00` twice. Both runs succeeded and the table held 25 rows for 2026-09-28, matching the file's 25 data rows, so the rerun didn't duplicate anything. The publish script wrote `reports/shipments_2026-09-28.csv` with 4 carriers. The static checker (`airflow_check.py`) exits 0, and its upcoming runs are 06:00 UTC daily from 2026-09-01.

**What it does**
- **Schedule:** it runs at 06:00 UTC and handles the day it fires. For example, the 2026-09-30 run waits for `shipments_2026-09-30.csv`. A manual trigger resolves to its trigger day, and you can pass a `day` param to rerun a specific date.
- **Wait for the file:** a reschedule-mode sensor reads `vendor_landing_dir` inside the task and checks every 10 minutes. It frees its worker slot between checks. The timeout is 18 hours, so a run that starts at 06:00 UTC fails at the end of that day if the file never arrives. That sensor timeout is not retried, so on-call gets the failure straight away.
- **Load:** one DuckDB transaction creates the table if needed, deletes that day's rows, and inserts the file's columns plus `ship_date`.
- **Publish:** `scripts/publish_shipments_report.sh` runs for the same date.
- **No backfill on deploy:** `start_date` is 2026-09-01 and `catchup=False`, so old days never run on their own. You can rerun any day since then by clearing a run or using `airflow backfill create`.
- **Existing DAG conventions:** it follows `warehouse_orders` for the owner, retries and warehouse path. I also set `max_active_runs=1` because DuckDB allows only one writer at a time.

**Not verified**
- **Late-file wait:** I only tested a day where the file already existed, so the sensor's rescheduling and timeout path didn't run.
- **Other run types:** I didn't test a manual trigger without a date.
- **Real directory:** I tested with `vendor_landing_dir` pointed at `data/incoming`, not your real landing directory.

**Leftovers:** `warehouse/` and `reports/` were created by the test. They're gitignored, so they won't be committed. I also created `output/af_home` as a scratch Airflow home, also gitignored. I haven't committed anything.