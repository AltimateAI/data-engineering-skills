# web-analytics-dags

Airflow 3.3 DAGs for the web analytics team.

- `dags/`: DAG files
- `data/clickstream/<YYYY-MM-DD>.csv.gz`: daily clickstream export from the web
  tracker, one file per UTC day. Columns: event_id, user_id (empty for
  anonymous hits), page, event_ts, load_ms, is_bot (1 = flagged by the bot filter).
- `data/marketing_spend.csv`: daily ad spend per channel
- `output/`: files loaded into the BI tool

Run a DAG locally with `airflow dags test <dag_id> <YYYY-MM-DD>`.
