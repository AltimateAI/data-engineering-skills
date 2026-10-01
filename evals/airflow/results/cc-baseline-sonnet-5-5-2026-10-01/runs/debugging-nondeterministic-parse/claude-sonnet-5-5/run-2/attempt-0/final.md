I fixed `dags/warehouse_ingest.py` so it no longer creates new versions on every parse, and it no longer calls the catalog service. I checked this by parsing the DAG three times and comparing the serialized output. There was no scheduler, so I didn't test it in a running Airflow.

The three symptoms had three separate causes, all in the parse-time code:

- **New version on every parse:**
  - `start_date=datetime.now() - timedelta(days=1)` changed on every parse. That is the one the warnings panel flagged.
  - The `description` also embedded `datetime.now()`.
  - I changed `start_date` to the fixed `datetime(2026, 1, 1)` and made the description static text. Existing runs aren't affected, since catchup is off.
- **`load_*` order changing between versions:** `TABLES = set(...)` iterates in a different order from one process to the next. It is now a de-duplicated list in file order (`dict.fromkeys`), so the tasks are always in the same order.
- **4-5 second parse and catalog requests:** parsing called the catalog with a 5 s timeout and 3 retries with backoff, on every parse. The DAG now reads only `config/tables.json`, which the deploy pipeline already refreshes on every release. I removed the HTTP call, the `CATALOG_URL` variable and the retry code.

Everything you asked to keep is unchanged. There is still one `load_<table>` task per table, chained `start → load_… → done` so they run one at a time, and the schedule is still `30 1 * * *`.

Here is what the three parses showed:
- The serialized DAG hash was identical each time.
- The task order was identical each time: `load_customers`, `orders`, `order_items`, `payments`, `refunds`, `shipments`, `products`, `inventory`.
- There were no import errors.
- The DAG-bag parse took about 2.2–2.7 s, but that is mostly Airflow's own startup. `warehouse_ingest.py` itself no longer does any waiting.

- **Behaviour change:** new tables now show up only after a release refreshes `config/tables.json`, not as soon as the catalog changes. If you need them to appear sooner, the catalog read should move into a scheduled task that updates the snapshot, not back into the parser.
- **README:** I updated it to say the DAG reads from the snapshot.
- **Existing versions:** the hundreds of old DAG versions stay in the metadata DB. New ones should stop appearing after the next dag-processor run.