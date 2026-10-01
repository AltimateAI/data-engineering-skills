# retail-finance-dags

Airflow 3.3 DAGs for the retail finance team.

- `dags/`: DAG files
- `data/orders.csv`: order export, refreshed continuously. `order_ts` is in UTC.
  Stores upload late orders up to about 02:00 UTC the next morning.
- `data/stores.csv`: store dimension
- `output/`: files picked up by the finance reporting tool

Run a DAG locally with `airflow dags test <dag_id> <YYYY-MM-DD>`.
