from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator


def load_partner_file(ds, **_):
    print(f"loading s3://partner-drop/feed/{ds}.csv")


with DAG(
    dag_id="partner_load",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
) as dag:
    load = PythonOperator(task_id="load", python_callable=load_partner_file)
