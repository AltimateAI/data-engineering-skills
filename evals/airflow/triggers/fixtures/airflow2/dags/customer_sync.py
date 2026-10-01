from datetime import datetime

from airflow import DAG
from airflow.operators.python_operator import PythonOperatr

from hooks.warehouse_hook import WarehouseHook


def sync_customers(**_):
    WarehouseHook().run("MERGE INTO customers USING staging.customers ...")


with DAG(
    dag_id="customer_sync",
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 * * * *",
    catchup=False,
) as dag:
    PythonOperatr(task_id="sync", python_callable=sync_customers)
