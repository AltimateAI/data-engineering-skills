I fixed `dags/warehouse_ingest.py`. It no longer creates a new version on every parse, and it no longer calls the catalog service from the parser.

**Causes**
- **Version churn:** two things changed on every parse. `start_date=datetime.now() - timedelta(days=1)` is the one the warnings panel flagged (line 65). The `description` also embedded `datetime.now()`.
- **Task order:** `TABLES = set(...)` iterates in a different order in each processor process, so the `load_*` tasks were chained in a different order each time. That also produces a new version.
- **Slow parse:** the DAG called the catalog service on every parse. If it was unreachable, the 3 retries with exponential backoff and a 5-second timeout stalled the parse. Note the service also feeds the set, so any change in its answer would create a version too.

**Changes**
- The DAG now reads only `config/tables.json`, which the deploy pipeline already refreshes on every release. The HTTP call, retries, `CATALOG_URL`, and the `os`, `time` and `urllib` imports are gone.
- The table list is built with `list(dict.fromkeys(...))`. That removes duplicates and keeps the file's order.
- `start_date` is now a fixed `datetime(2026, 1, 1)`, and the description is a static string.
- The schedule (`30 1 * * *`, UTC), `catchup=False`, one `load_<table>` task per table, and the one-after-another `chain(start, *loads, done)` are unchanged.

**Checked**
- `airflow_check.py` exits 0 and the next runs are 01:30 UTC. Its one warning only notes that a cron string runs at the time it fires. The tasks don't use run dates, so it doesn't apply.
- I parsed the DAG in 3 separate processes with random hash seeds. The serialized DAG was byte-identical each time, and the task order was always `start`, `load_customers` through `load_inventory` in file order, then `done`.
- `airflow dags test warehouse_ingest 2026-03-02T01:30:00+00:00` ended in `success`. The load tasks ran one after another. Tasks I saw loading rows: shipments (6), products (8), inventory (3).
- Each parse took about 2 seconds in my run, and most of that is importing Airflow. I did not time it against the old version.

**Not checked**
- I couldn't run a scheduler here, so I haven't seen the version count stay flat in the UI. Existing versions stay in the history. The next parse will add one more version (the DAG definition changed), and after that it should stay flat.
- The DAG now only picks up catalog changes when `config/tables.json` is redeployed. That's what the README already says the deploy pipeline does. If the snapshot can lag the real catalog, a separate job should refresh it rather than the parser.

I removed the scratch files from my test runs. `dags/warehouse_ingest.py` is the only modified file, and nothing is committed.