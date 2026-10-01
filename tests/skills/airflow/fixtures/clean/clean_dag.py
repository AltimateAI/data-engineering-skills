from datetime import datetime

from airflow import DAG

try:
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:
    from airflow.operators.bash import BashOperator

with DAG(
    "clean_daily",
    schedule="30 2 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["fixture"],
):
    extract = BashOperator(task_id="extract", bash_command="echo extract")
    load = BashOperator(task_id="load", bash_command="echo load")
    extract >> load
