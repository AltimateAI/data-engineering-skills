from datetime import datetime

from airflow import DAG

try:
    from airflow.providers.standard.operators.empty import EmptyOperator
except ImportError:
    from airflow.operators.empty import EmptyOperator

with DAG("still_good", schedule="@daily", start_date=datetime(2026, 1, 1), catchup=False):
    EmptyOperator(task_id="noop")
