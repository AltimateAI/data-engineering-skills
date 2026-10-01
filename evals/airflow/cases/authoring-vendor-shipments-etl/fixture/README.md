# logistics-pipelines

Airflow DAGs for the logistics analytics team.

- `dags/` holds the DAGs. The project runs on Airflow 3.3 (see `requirements.txt`).
- The local warehouse is a DuckDB file at `warehouse/analytics.duckdb`. DAGs create
  their tables on first use.
- `scripts/` has helper scripts that DAGs call.
- `data/` has sample inputs for local development.

Local development:

```bash
pip install -r requirements.txt
airflow dags test <dag_id> <YYYY-MM-DD>
```
