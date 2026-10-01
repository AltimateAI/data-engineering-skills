# targets: 2.11
# near-miss: removed-dag-kwarg, removed-kwarg, sla-ignored
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

with DAG(
    "legacy_ok_on_2x",
    schedule_interval="0 6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"sla": timedelta(hours=1)},
):
    PythonOperator(task_id="p", python_callable=print, provide_context=True, sla=timedelta(hours=2))
