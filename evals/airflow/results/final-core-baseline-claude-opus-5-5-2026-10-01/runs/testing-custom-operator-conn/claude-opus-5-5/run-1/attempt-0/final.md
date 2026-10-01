I added tests for the hook and operator in `tests/`, and they run with plain `pytest tests/`. All 13 pass, and I didn't touch the hook or operator code.

**How the connection is supplied:** each test sets its own connection through an `AIRFLOW_CONN_<ID>` environment variable pointing at a DuckDB file in a temporary folder. The variable is removed after each test, so CI needs no Airflow connections, no Airflow database and nothing else running. DuckDB isn't mocked; `execute()` runs for real against that temporary file.

**Files:**
- `tests/conftest.py` puts `dags/` on the import path so `from warehouse.hooks import ...` works the same way it does in the DAGs. It also provides a helper that creates one of these connections.
- `tests/test_hooks.py` (5 tests) checks that the hook:
  - takes the file path from the connection's host and the schema from its schema field
  - falls back to `main` when no schema is set
  - raises an error when there's no host
  - writes to the configured file
  - respects the read-only setting in the extras
- `tests/test_operators.py` (8 tests) runs `execute()` against a small test CSV. It checks:
  - **Only the requested partition is loaded:** the returned count matches, only that date's rows are in the table, all columns land, and they go into the schema from the connection.
  - **Re-running is safe:** running the same date twice gives the same count with no duplicates, and a corrected CSV replaces that date's rows.
  - **Other dates are left alone:** re-running one date keeps another date's rows even when the new CSV no longer contains them. A date with no rows returns 0.
  - **The given connection is used:** a decoy connection is registered under the default name `duckdb_warehouse`, and the test asserts that its file is never created. Two connections with different files and schemas each write only to their own.

**Checking that the tests catch bugs:** I broke the operator three ways, one at a time, and reverted each with git:

| Change to the operator | Result |
|---|---|
| Removed the `DELETE` | 3 tests fail (duplicates, replacement, other dates) |
| Dropped the date filter on the `INSERT` | 8 tests fail |
| Made it ignore `duckdb_conn_id` | 8 tests fail |

I also ran the tests with all of this machine's `AIRFLOW_*` variables removed, to mimic CI, and they still pass. Without `AIRFLOW_HOME`, Airflow falls back to `~/airflow` and may create that folder on the runner, which is harmless.

The tests are untracked in `tests/` and not committed yet.