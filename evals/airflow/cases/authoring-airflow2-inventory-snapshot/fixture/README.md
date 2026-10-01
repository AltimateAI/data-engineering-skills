# supply-chain-dags

DAGs for the supply-chain analytics team, deployed to our managed Airflow
environment (versions are pinned in `requirements.txt`).

- `dags/`: DAG files
- `data/`: nightly CSV extracts (`inventory_movements.csv`, `reorder_points.csv`, `sales.csv`)
- `output/<dag_id>/<ds>.csv`: DAG outputs, one file per logical date

Try a DAG locally with `airflow dags test <dag_id> <YYYY-MM-DD>`.
