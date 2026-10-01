# analytics-dags

Airflow 3.3 DAGs for the analytics team.

- `dags/order_status_report.py`: daily order counts per status (CSV in `output/`).
- `dags/warehouse_load.py`: daily revenue per region into the DuckDB warehouse
  (being moved over from the old Airflow 2 box).

Airflow Variables (set per environment, e.g. `airflow variables set ...`):

| Variable | Meaning |
|---|---|
| `warehouse_path` | directory holding `warehouse.duckdb` |

Local development: `pip install -r requirements.txt`, then point
`AIRFLOW__CORE__DAGS_FOLDER` at `dags/`.
