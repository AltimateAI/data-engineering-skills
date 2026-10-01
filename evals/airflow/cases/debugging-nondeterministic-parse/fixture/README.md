# warehouse-dags

Airflow 3.3 DAGs that load the nightly raw extracts (`data/raw/*.csv`) into the
DuckDB warehouse (`warehouse/warehouse.duckdb`).

- `dags/warehouse_ingest.py`: one `load_<table>` task per table registered in
  the platform team's catalog service (`CATALOG_URL`).
- `config/tables.json`: copy of the catalog that the deploy pipeline refreshes
  on every release.

Local run: `airflow dags test warehouse_ingest 2026-03-02`.
