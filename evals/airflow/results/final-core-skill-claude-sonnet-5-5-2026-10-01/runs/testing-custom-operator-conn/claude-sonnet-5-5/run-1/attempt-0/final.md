I added `tests/conftest.py` and `tests/test_warehouse.py`, and `pytest tests/ -q` gives 12 passed in about 2 seconds. I ran it with Airflow 3.3.2 and DuckDB 1.5.6 in the local env, with no connections configured.

Nothing under `dags/` changed. `git status` shows only the new `tests/` directory.

**How the tests run without CI setup**
- `conftest.py` sets a throwaway Airflow home and metadata DB before Airflow is imported. It also puts `dags/` on `sys.path`.
- Each test sets its own connection through an `AIRFLOW_CONN_TEST_WH` environment variable.
- That id differs from the hook default (`duckdb_warehouse`) and the DAG's id (`warehouse`), and the tests remove those two env vars. An operator that ignored the `duckdb_conn_id` it was given would therefore fail.
- `execute()` runs for real against a DuckDB file in `tmp_path`, and the tests read the table back to check its contents.

**Your contract, test by test**
- **Hook settings:** the DuckDB path comes from `host` and the schema from `schema`. The schema defaults to `main`, a missing host raises, and `read_only` in the connection extra is honored.
- **Operator conn id:** it uses whatever `duckdb_conn_id` it is given. This is checked on a second file and schema.
- **Partition load:** only the `partition_date` rows are loaded and `execute()` returns that count. An empty partition returns 0. The table is created in the connection's schema.
- **Re-running a partition:** it replaces that partition's rows with no duplicates, including when the CSV contents changed. Other dates are left alone.
- **SQL injection:** a hostile partition value is not interpolated into the SQL.

**Mutation check:** I planted 8 bugs, and every one made a test fail. They covered ignoring the connection's schema, reading the path from the wrong field, a `read_only` default flip, a hard-coded conn id, a `DELETE` that removes nothing or the wrong rows, an `INSERT` that loads every row, and a wrong return value.

The mutated runs left stray files named `raw` and `s2` in the repo root, so I deleted them. They're gone, and the tests themselves don't write outside `tmp_path`.

**Not verified:** real Airflow connections, scheduler or `dag.test()` runs of `load_raw_sales`, and other Airflow versions. I didn't add tests for the DAG itself because you only asked for the hook and operator.