I fixed `dags/warehouse_ingest.py` so it parses the same way every time and no longer calls the catalog service. I couldn't test against a scheduler or metadata DB, because the local Airflow DB isn't migrated. I loaded the file with `DagBag` under two different `PYTHONHASHSEED` values instead. Both runs gave identical results: no import errors, the same task order, and a parse time of about 0.04s.

**What was wrong**
- **Version churn:** `start_date=datetime.now() - timedelta(days=1)` and a `description` containing `datetime.now()` and the table count changed on every parse. That is the warning at line 65, and each change produced a new DAG version.
- **Task order changing:** `TABLES = set(...)` was ordered by Python's per-process hash seed. The `load_*` tasks, and the chain order between them, therefore changed from one processor run to the next.
- **Slow parse and catalog traffic:** `list_tables()` made an HTTP call at import time, with 5s timeouts and exponential-backoff retries. Whenever the service was unreachable, that alone cost seconds per parse.

**What I changed**
- `start_date` is now the fixed `datetime(2026, 1, 1, tzinfo=timezone.utc)`, and `description` is a static string.
- `TABLES` is now built from `config/tables.json` only, with `dict.fromkeys` to drop duplicates while keeping the file's order. The HTTP call, retries, `CATALOG_URL`, and the `os`, `time` and `urllib` imports are gone.
- I updated the README line that referred to `CATALOG_URL`.
- The graph is still `start → load_<table> → … → done`, one `load_<table>` per table, run in series. The schedule is still `30 1 * * *`.

**Things to know**
- **Catalog source:** the table list now comes only from `config/tables.json`, which the deploy pipeline refreshes on every release. A table added to the catalog won't appear until the next deploy. If you need it to track the catalog sooner, fetch it at run time inside a task rather than in the parser. That would mean a dynamic task list, so the per-table tasks would no longer all be defined up front.
- **One more version bump:** you'll get one new DAG version when this deploys, because the `start_date` and `description` values change. After that it should stay stable. Note that the existing 1:1 hundreds of old versions stay in the history.
- **Timezone:** the schedule is evaluated in Airflow's default timezone. I didn't check whether your deployment overrides it from UTC.