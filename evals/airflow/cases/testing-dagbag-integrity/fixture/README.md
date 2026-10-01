# acme-data-platform

Airflow 3.3 DAGs for the analytics warehouse (local DuckDB file in dev).

- `dags/` - DAG files.
- `data/` - sample exports used in dev.
- `output/` and `warehouse.duckdb` are created by the DAGs and are git-ignored.

Local run:

```bash
pip install -r requirements.txt
airflow dags test orders_ingest 2026-03-02
```
