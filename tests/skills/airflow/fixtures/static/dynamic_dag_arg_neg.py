# targets: 3.3 2.11
# near-miss: dynamic-dag-arg
from datetime import datetime, timedelta

import pendulum
from airflow import DAG
from airflow.decorators import dag, task

default_args = {"owner": "data", "retries": 2, "retry_delay": timedelta(minutes=5)}
START = pendulum.datetime(2026, 1, 1, tz="UTC")

with DAG(
    dag_id="report_fixed",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    default_args=default_args,
    catchup=False,
):
    pass


@task
def stamp():
    return datetime.now().isoformat()


@dag(schedule="@hourly", start_date=START, catchup=False)
def hourly_fixed():
    stamp()


hourly_fixed()
