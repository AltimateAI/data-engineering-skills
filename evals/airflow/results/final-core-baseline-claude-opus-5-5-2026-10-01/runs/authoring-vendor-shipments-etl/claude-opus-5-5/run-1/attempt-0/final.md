I added the DAG in `dags/vendor_shipments.py`. I ran it locally with `airflow dags test` on the sample file for 2026-09-28: it loaded 25 rows, a second run still left 25 rows rather than 50, and it published the report. Nothing is committed yet.

**How it works**
- **Schedule:** runs at `0 6 * * *`, starting 2026-09-01 with `catchup=False`, so deploying it won't backfill September. You rerun a day by triggering with that date, e.g. `airflow dags trigger vendor_shipments -l 2026-09-15`, or by clearing an existing run. It uses the same owner, retry settings and project paths as `warehouse_orders`. `ds` is the run's own date, which I confirmed in the test.
- **1. Waiting for the file:** a small custom sensor checks for `{{ var.value.vendor_landing_dir }}/shipments_{{ ds }}.csv`. If the file isn't there, it hands the wait to the triggerer, so it doesn't hold a worker slot. It gives up at midnight UTC at the end of that date, not after a fixed number of hours. So a run that starts late or retries still fails at end of day. If you rerun an old day and its file is gone, it fails straight away instead of waiting 18 hours; I tested that with 2026-09-27, which has no sample file. I didn't use the stock `FileSensor` because it needs an `fs_default` connection in every environment. I didn't test the actual overnight wait, since that would mean waiting until midnight.
- **2. Loading:** the table has the file's five columns with fixed types (`weight_kg DOUBLE`, `shipped_at TIMESTAMP`) plus `ship_date DATE`. The load deletes that day's rows and inserts the new ones in a single transaction, so a rerun replaces the day instead of adding duplicates. I fixed the column types because letting DuckDB guess them per file could, for example, make `weight_kg` a whole-number column on a day when every weight happens to be a whole number.
- **3. Publishing:** runs `scripts/publish_shipments_report.sh {{ ds }}`. That script already fails if the day has no rows, so an empty file also causes a page.

**Things to know**
- **You need to set something up:**
  - Each environment needs the `vendor_landing_dir` Variable.
  - A triggerer process must be running, or the wait will never finish.
  - Paging only happens if a failed task already triggers it; the existing DAG has no failure callback, so I didn't add one.
- **Possible half-written file:** the sensor fires as soon as the file exists. If the aggregator writes it slowly rather than moving it into place when finished, a partial file could be loaded. A later rerun fixes that day, but if this is a risk, ask them for a marker file (such as `.done`) and wait on that instead.
- **Column order:** the load reads columns by position, not by name. If the vendor reorders or adds columns, the load will either error or put values in the wrong columns.

I deleted everything the test runs created (warehouse, reports, a stray `airflow.cfg`), so the only change in the repo is the new DAG file.