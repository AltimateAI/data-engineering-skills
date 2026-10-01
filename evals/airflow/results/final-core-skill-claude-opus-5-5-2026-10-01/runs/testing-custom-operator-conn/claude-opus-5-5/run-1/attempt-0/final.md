I added 11 unit tests in `tests/`, and `pytest tests/ -q` passes them all (11 passed in about 2.6s). They need no Airflow connections, no metadata database and nothing else running. The hook and operator code are unchanged, and `git status` shows only the new `tests/` folder.

**How the connection is supplied:** each test sets `AIRFLOW_CONN_<ID>` as JSON pointing at a DuckDB file in pytest's temporary folder. The tests use connection ids that aren't the code's defaults (`duckdb_warehouse`, or `warehouse` in the DAG), and those defaults are removed from the environment. So an operator that ignored the `duckdb_conn_id` it was given would fail instead of quietly passing. `execute()` runs for real against the DuckDB file, and the tests check by opening that file and reading the table, not just by looking at the return value.

**What each part of your contract is checked by:**
- **Path from host, schema from schema:** `test_hook_reads_path_from_host_and_schema_from_schema` and `test_hook_get_conn_opens_the_file_from_host` (writes through the hook, then reads the file back). `test_execute_writes_into_the_connection_schema` checks the table lands in the connection's schema.
- **Uses the conn id it's given:** `test_hook_uses_the_conn_id_it_is_given` and `test_operator_uses_the_conn_id_it_is_given`. The second sets up two connections and checks that only the right file gets written and the other is never created.
- **Only `partition_date` rows load, and the return value is the count:** `test_execute_loads_only_the_partition_date` checks exact rows and values, not just the count. `test_execute_date_with_no_rows_loads_nothing` covers a date with no rows (returns 0).
- **Re-runs replace without duplicates and leave other dates alone:** `test_rerun_replaces_partition_and_leaves_other_dates_alone`. It loads three dates, then corrects the CSV for one date (a row dropped, one changed, one added) and reloads that date twice. It checks the final table exactly.
- **Extra cases from the hook's own docstring:** the schema defaults to `main`, a missing host raises `ValueError`, and `{"read_only": true}` opens the file read-only.

**Checking the tests catch bugs:** I temporarily planted 11 small bugs in the hook and operator, one at a time, and the suite caught all 11. The code was put back exactly as it was each time. The bugs included:
- ignoring the conn id
- falling back to an in-memory database
- ignoring the connection's schema
- loading dates on or after the partition instead of just that date
- dropping or widening the delete before the reload
- counting the whole table instead of the partition

**Things to know:**
- Only the re-run test catches a wrong count from `execute()`, because it's the only one with other dates already in the table.
- The tests use small CSV files they create themselves, not `data/*.csv`.
- I didn't run the `load_raw_sales` DAG end to end, and I only ran the tests on the installed Airflow 3.3.2 with DuckDB 1.5.6.