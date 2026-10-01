# targets: 3.3 2.11
from datetime import datetime, timedelta

import pendulum
from airflow import DAG
from airflow.decorators import dag
from airflow.utils.dates import days_ago

default_args = {"owner": "data", "start_date": days_ago(1)}  # expect: dynamic-dag-arg
RUN_TAG = datetime.now().strftime("%Y%m%d")  # expect: dynamic-dag-arg

with DAG(
    dag_id=f"report_{RUN_TAG}",
    schedule="@daily",
    start_date=datetime.now() - timedelta(days=1),  # expect: dynamic-dag-arg
    default_args=default_args,
    catchup=False,
):
    pass


@dag(schedule="@hourly", start_date=pendulum.now("UTC"), catchup=False)  # expect: dynamic-dag-arg
def hourly_pipeline():
    pass


hourly_pipeline()
