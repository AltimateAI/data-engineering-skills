I added tests for the hook and operator, and `pytest tests/` passes (10 tests). I didn't touch the hook or operator code.

- **Connections:** `tests/test_warehouse.py` supplies connections through `AIRFLOW_CONN_<ID>` env vars, set with `monkeypatch` per test. That needs no metadata DB and no configured connections. I only ran it here, not in a CI environment.
- **Imports:** `tests/conftest.py` puts `dags/` on `sys.path`, so `from warehouse...` resolves the same way it does in the DAGs.
- **Real DuckDB:** `execute()` runs against a temporary `.duckdb` file under `tmp_path`, with real CSVs written per test. Assertions read the file back through a separate DuckDB connection.

**Hook tests:**
- It takes the file path from `host` and the schema from the connection's schema field.
- The schema defaults to `main`.
- A missing `host` raises `ValueError`.
- `read_only` in extra makes writes fail.

**Operator tests:**
- Only the `partition_date` rows load, and `execute()` returns that count.
- Re-running the same partition leaves no duplicates.
- Re-running with a changed source replaces that partition's rows and leaves other dates alone.
- If the partition is absent from the new source, it returns 0 and clears the existing rows.
- The operator uses whatever `duckdb_conn_id` it is given: a second connection with another file and schema gets the data, and the first file is never created.
- The default `duckdb_conn_id` is the hook's default.