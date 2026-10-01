from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator


def build_report(execution_date, next_ds, **_):
    print(f"building weekly report for {execution_date:%Y-%m-%d} .. {next_ds}")


with DAG(
    dag_id="weekly_report",
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 7 * * MON",
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5), "sla": timedelta(hours=2)},
) as dag:
    start = DummyOperator(task_id="start")
    report = PythonOperator(task_id="build_report", python_callable=build_report, provide_context=True)
    start >> report
