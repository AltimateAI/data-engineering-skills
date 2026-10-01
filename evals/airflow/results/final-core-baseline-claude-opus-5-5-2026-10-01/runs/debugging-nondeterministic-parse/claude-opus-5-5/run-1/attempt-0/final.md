`warehouse_ingest` now builds the same DAG version on every parse, and parsing takes about 0.04s instead of about 4.6s. I changed `dags/warehouse_ingest.py` and the README, and haven't committed anything.

**What was wrong** (I reproduced all three by parsing the original file under different hash seeds; every parse produced a different version):
1. **`start_date=datetime.now() - timedelta(days=1)` and the `datetime.now()` in `description`** gave each parse new values. That's the Line 65 warning.
2. **`TABLES = set(...)`**: Python iterates a set of strings in a different order in each process. That's why the `load_*` tasks moved around in the graph view, and since `chain()` links them in that order, the actual dependencies changed too. The DAG warning doesn't catch this one, so fixing the warning alone wouldn't have stopped the new versions.
3. **The catalog HTTP call at import time**: every parse on every processor made a request. When the service wasn't reachable, the retry backoff slept 1.5s + 3s before falling back to `config/tables.json`, which is where the 4–5s came from.

**The fix:**
- The parser now reads only `config/tables.json`, which the deploy pipeline already refreshes on every release. I removed the catalog call and `CATALOG_URL`, so the platform team's service gets no requests from the parser.
- `TABLES = sorted(set(...))` still removes duplicate tables and now always gives the same order.
- `start_date` is fixed at `datetime(2026, 1, 1, tzinfo=timezone.utc)`, and the timestamp is gone from `description`. `catchup=False` is unchanged, so nothing gets backfilled.

**What I checked:**
- Five parses with different hash seeds all produced the same version hash, using Airflow's own `SerializedDagModel.hash`.
- Airflow's own check for this warning flags the original file at Line 65 and reports nothing on the new one.
- There is still one `load_<table>` task per table, chained one after another: `start → load_customers → … → load_shipments → done`.
- The schedule resolves to `30 1 * * *` in UTC.
- `airflow dags test warehouse_ingest 2026-03-02` finished with every task successful. I used a throwaway `AIRFLOW_HOME` and deleted it, along with the `warehouse/` output from the test run.

**Things to know:**
- **Table list only changes on deploy:** a table added to the catalog appears after the next deploy refreshes `tables.json`, not on the next parse. That's also the only time the DAG version will change now. If the pipeline ever stops refreshing that file, the DAG will be out of date.
- **New load order:** the loads now run alphabetically. The old order was random, so nothing depended on it.
- **Old versions stay:** the hundreds of versions already created remain in the version history. Expect one more version when this deploys, then none until the table list or the DAG changes.