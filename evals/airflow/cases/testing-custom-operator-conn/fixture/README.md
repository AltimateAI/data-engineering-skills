# sales-warehouse

Airflow 3.3 project that loads the nightly sales exports into a DuckDB warehouse.

- `dags/load_raw_sales.py` - loads `data/orders.csv` and `data/refunds.csv` one day at a time.
- `dags/warehouse/` - our DuckDB hook and the CSV partition loader operator
  (listed in `dags/.airflowignore` so the DAG processor does not parse it as DAGs).

The DAG uses the `warehouse` connection. For a local run:

```bash
export AIRFLOW_CONN_WAREHOUSE='{"conn_type": "duckdb", "host": "/tmp/warehouse.duckdb", "schema": "raw"}'
airflow dags test load_raw_sales 2026-03-02
```
