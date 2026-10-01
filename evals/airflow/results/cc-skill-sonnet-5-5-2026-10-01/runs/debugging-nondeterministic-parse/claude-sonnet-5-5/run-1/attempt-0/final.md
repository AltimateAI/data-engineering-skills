I fixed `dags/warehouse_ingest.py`, so it should stop creating new versions. The parse itself is quick now. I checked the parse output and a local test run, but not a second parse of the same file to confirm the version stays put.

**What was wrong**
- **New version on every parse:** `start_date=datetime.now() - timedelta(days=1)` and a `description` containing `datetime.now()` both change on every parse. That is what the warnings panel flagged. The description also embedded the table count.
- **Task order changing:** `TABLES = set(...)` has no stable order. Python randomises string hashing per process, so each dag-processor produced a different `load_*` order, which changes the serialized DAG.
- **Slow parse and catalog traffic:** `list_tables()` called the catalog service on every parse. When it was unreachable it retried with backoff of about 1.5 s plus 3 s, and with a 5 s timeout per attempt it could run to many seconds before falling back to the snapshot. That explains the 4–5 s parse.

**What I changed**
- The parser now reads only `config/tables.json`, which the deploy pipeline already refreshes on every release. There is no network call, no `CATALOG_URL` and no retries.
- Duplicates are removed with `dict.fromkeys`, so the order is the snapshot's order on every parse.
- `start_date` is fixed at `2026-01-01 UTC` and the `description` is static.
- `README.md` now says the parser reads only the snapshot.

**What I kept**
- **Tasks:** one `load_<table>` per table, plus `start` and `done`.
- **Order:** the loads still run one after another via `chain`.
- **Schedule:** still `30 1 * * *`, which Airflow reports as `30 1 * * *`, and `catchup=False`. Nothing else in the file uses the timezone, so it stays UTC.

**What I checked**
- **Task order:** under three different `PYTHONHASHSEED` values the table order is identical.
- **Import:** it imports with no errors.
- **Parse time:** the DagBag parse took about 2.4 s in total, which includes importing Airflow itself.
- **Task list and sequence:** the DagBag lists all 8 `load_*` tasks, and its topological order runs `start`, then the loads one by one, then `done`.
- **Local run:** `airflow dags test warehouse_ingest 2026-03-02` began loading tables successfully. I only inspected the first few of the 8 in the output, and I removed the artifacts it created.

I did not run the bundled `airflow_check.py` script, because the path I tried for it didn't exist.

**Two things to know**
- **One last version bump:** the first parse after you deploy this will create one more DAG version, since the serialized DAG changes. After that it should stay put.
- **Snapshot staleness:** a table added to the catalog now shows up only when the deploy pipeline refreshes `tables.json`, not within minutes. If that lag is a problem, the alternative is a task that fetches the list at run time, but then it can't create one task per table in advance.

I haven't committed anything.