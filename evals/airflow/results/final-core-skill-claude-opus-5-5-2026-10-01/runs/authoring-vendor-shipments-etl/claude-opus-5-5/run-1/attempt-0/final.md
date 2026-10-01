I've added `dags/vendor_shipments.py` and ran it locally on Airflow 3.3.2, the version in `requirements.txt` and the one installed. Every case below behaved as expected. Nothing is committed.

**Which day each run processes (UTC):**
- **Scheduled run at 06:00:** that day's file. The 2026-10-02 run loads `shipments_2026-10-02.csv`.
- **Reruns:** clearing a past run, or `airflow backfill create` for a date range, reprocesses that run's own day.
- **Manual trigger:** set the `day` param (e.g. `{"day": "2026-09-14"}`) to reprocess any day. Without it, the run processes the day it was triggered. Days before 2026-09-01 are rejected.
- **Deploy:** `catchup=False` and `start_date=2026-09-01`, so nothing old runs on its own. Only the latest 06:00 run gets scheduled once.

**How it works:**
1. **`wait_for_file`** checks every 10 minutes for `<vendor_landing_dir>/shipments_<day>.csv`. It gives up its worker slot between checks. The Variable is read inside the task, not when the DAG file is parsed. If the file isn't there by midnight UTC at the end of that day, the task fails straight away, with no retries, so on-call gets paged.
2. **`load_shipments`** creates `vendor_shipments` in `warehouse/analytics.duckdb` if needed. Columns are `shipment_id`, `carrier`, `destination`, `weight_kg`, `shipped_at` plus `ship_date`. In one transaction it deletes that day's rows and inserts the file, so a rerun replaces the day instead of duplicating it.
3. **`publish_shipments_report`** runs `scripts/publish_shipments_report.sh <day>` with an absolute path, like `refresh_orders_mart` does.

It follows `warehouse_orders` for paths, `default_args`, task styles and the delete-then-insert pattern.

**What I tested:**
- **Static checker:** no errors. The next runs are at 06:00 UTC daily, each for its own day. The one warning is about the `now()` call, which only enforces the end-of-day deadline and never picks which day to load.
- **Run for 2026-09-28 with the sample file, twice:** both succeeded. The table had 25 rows for that day after each run (no duplicates), and the report listed 4 carriers.
- **Run for 2026-09-29, where there's no file:** failed in about 5 seconds with no retries.
- **Manual triggers:** with `day=2026-09-28`, without a param, and with `day=2026-08-15`. The first two succeeded; the last was rejected as expected.

I removed all the local test outputs afterwards.

**Not tested:**
- A real scheduler waiting for hours before the file arrives.
- Your actual landing directories. Set the `vendor_landing_dir` Variable in each environment before the first run, or the wait task will fail.

**Problem in the existing DAG (not changed):** `warehouse_orders` uses `ds`, which isn't set when a run is triggered manually on Airflow 3 without a date. Those manual runs will fail. The fix is small and I can make it if you'd like.