`warehouse_ingest` now parses in about 0.04 s instead of 4.6 s and gives the same DAG on every parse, so it should stop creating new versions. It no longer contacts the catalog service while parsing. I made the changes in `dags/warehouse_ingest.py` and updated the README to match; nothing is committed.

**What was wrong** (I reproduced all three symptoms before changing anything):
1. **New version on every parse:** the `DAG(...)` call used `datetime.now()` twice, once in `description` (the line the warnings panel flagged) and once in `start_date`. Every parse therefore produced a different DAG.
2. **`load_*` order changing:** `TABLES = set(...)`. A Python set comes out in a different order in each process, so each parse built a different chain. Two parses of the old file gave different load orders and different DAG hashes.
3. **Slow parse and catalog traffic:** every parse called `CATALOG_URL`. When the call failed, it retried with 1.5 s + 3 s of back-off and then fell back to `config/tables.json`, which accounts for the 4–5 s.

**What I changed:**
- **Table list:** it is read only from `config/tables.json`, the snapshot your deploy pipeline refreshes on each release. Repeated entries are dropped and the file order is kept.
- **DAG arguments:** fixed values. The description is "Load 8 raw tables from the catalog snapshot" and `start_date` is 2026-01-01 UTC.
- **Schedule:** written explicitly as `CronTriggerTimetable("30 1 * * *", timezone="UTC")`, so it stays at 01:30 UTC whatever the cluster's default timezone is. The checker's preview shows runs at 01:30 UTC on Oct 1, 2 and 3.
- **Unchanged:** one `load_<table>` task per table, run one after another as `start → load_customers → load_orders → … → load_inventory → done`. `catchup=False` and the tags are the same.

**What I tested** (Airflow 3.3.2 in a throwaway local environment):
- **Same DAG every time:** I parsed the file in three separate processes, each with a different Python hash seed. All three gave the same hash and the same task order.
- **No new versions:** after three reserialize runs plus two `dags test` runs, the metadata DB held one version of `warehouse_ingest`.
- **Checker:** the skill's checker exited clean. Its one warning is about which day `{{ ds }}` refers to, and it doesn't apply because the loads don't use dates.
- **Execution:** `airflow dags test warehouse_ingest 2026-10-01T01:30:00+00:00` succeeded twice in a row, and a separate manual-trigger run also succeeded. All 8 `raw_*` tables were loaded, and the second run gave the same row counts because each load replaces its table. I deleted the `warehouse/` folder the test runs created.

**Things to know:**
- **Fixing the existing copy:** you'll see one last new version when this is deployed, because the DAG itself changed. After that it should stay on that version. The hundreds of old versions stay in the history.
- **When catalog changes take effect:** new tables show up in the DAG only when the deploy pipeline refreshes `config/tables.json`, not within seconds as before. If you need it faster, a small scheduled job could rewrite that file from the catalog. That would still keep requests out of the parser.

I haven't checked this against a real dag-processor or scheduler, since neither runs locally.