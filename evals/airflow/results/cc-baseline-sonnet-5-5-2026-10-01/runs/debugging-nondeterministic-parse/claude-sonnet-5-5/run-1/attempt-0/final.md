I fixed `dags/warehouse_ingest.py`. The serialized DAG hash is now identical across two parses a minute apart (`af646eab…`), so the dag-processor should stop creating new versions. I checked the hash and parse time by loading the DAG with `DagBag`. I couldn't run a full `airflow dags` flow because the local Airflow DB isn't migrated.

**What was wrong**
- **Version churn:** the DAG constructor had `start_date=datetime.now() - timedelta(days=1)` and a `description` containing `datetime.now()`. Both change on every parse, so every parse looked like a new DAG version. That is the warning on line 65.
- **Task order:** `TABLES = set(list_tables())` has no stable order, so the `load_*` chain was shuffled between parses. Because of that, the order differed between versions.
- **Slow parse:** `list_tables()` called the catalog service at import time, with a 5s timeout and 3 retries with backoff. When the service was unreachable or slow, the parse took 4–5s. Every parser run also sent a request to the catalog.

**What I changed**
- The parser no longer calls the catalog. It reads only `config/tables.json`, the snapshot the deploy pipeline already refreshes on each release. I removed the HTTP call, retries, `CATALOG_URL` and the unused imports.
- Tables are de-duplicated with `dict.fromkeys`. That keeps catalog order and still drops the occasional double listing.
- `start_date` is fixed at `datetime(2026, 1, 1, tzinfo=timezone.utc)`.
- The description is now just `Load N raw tables`, without the timestamp.

**What stayed the same**
- There is one `load_<table>` task per table (8 of them).
- The loads still run one after another between `start` and `done`.
- The schedule is still `30 1 * * *`. The UTC start date makes that 01:30 UTC.

**Verification:** the DAG imports with no errors. Parse time is about 0.05–0.12s, down from 4–5s. The task list and order are the same on both runs: `load_customers → orders → order_items → payments → refunds → shipments → products → inventory`.

**Things to know**
- Adding or removing a table now takes effect when the deploy pipeline refreshes `tables.json`, not when the catalog changes. That is a deliberate trade-off to keep the catalog out of the parser. If the platform team needs a live view, do that in a separate task at run time.
- The new start date and the dropped description timestamp produce one final new version on deploy. After that it should stay stable.
- Reordering or editing `tables.json` will also create a version, but only at release time.
- The old fallback in `list_tables()` was already the same file read, so behaviour when the catalog was down is unchanged.

I didn't commit anything.