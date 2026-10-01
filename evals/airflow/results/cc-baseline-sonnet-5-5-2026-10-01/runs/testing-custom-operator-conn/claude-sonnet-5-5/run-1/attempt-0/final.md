I added 11 tests, and `pytest tests/` passes them all (11 passed, about 2s). I didn't change the hook or operator.

**How they run in CI**
- `tests/conftest.py` puts `dags/` on `sys.path`, so `warehouse.*` imports the way it does in the DAGs.
- Each test supplies its own connection through an `AIRFLOW_CONN_<ID>` environment variable, set with `monkeypatch`. That needs no Airflow database or configured connections, and the variable is removed after each test.
- `execute()` runs against a real DuckDB file in `tmp_path`, with nothing mocked. The tests read the results back with a separate DuckDB connection.

**What `tests/test_duckdb_warehouse.py` covers**
- **Hook:**
  - It takes the file path from `host` and the schema from `schema`.
  - The schema defaults to `main`.
  - A missing `host` raises `ValueError`.
  - `get_conn()` opens the file.
  - `extra={"read_only": true}` blocks writes.
- **Operator:**
  - Only the requested partition is loaded, and `execute()` returns that row count.
  - It uses the `duckdb_conn_id` it is given. With two connections, only the chosen database file is created.
  - Rows go to the connection's schema.
- **Idempotency:**
  - Re-running a partition leaves no duplicates.
  - A re-run replaces changed rows in that partition and leaves other dates untouched.
  - A partition missing from the CSV returns 0 and leaves existing rows alone.

`pytest` isn't in `requirements.txt`, so CI needs it installed separately.