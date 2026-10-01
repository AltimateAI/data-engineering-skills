# partner-integrations

Airflow 3.3 DAGs that ingest data sent to us by marketplace partners.

- `dags/`: DAG files
- `data/partner_drop/<YYYY-MM-DD>/<partner>.csv`: files partners upload over SFTP,
  one folder per business date (sample days included for local testing)
- `data/partners.json`: partner registry
- `output/`: DAG outputs

Run a DAG locally with `airflow dags test <dag_id> <YYYY-MM-DD>`.
