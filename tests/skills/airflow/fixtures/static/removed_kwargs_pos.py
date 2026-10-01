# targets: 3.3
from datetime import datetime

from airflow import DAG
from airflow.decorators import dag
from airflow.operators.python import PythonOperator
from airflow.timetables.interval import CronDataIntervalTimetable

with DAG(
    "legacy_kwargs",
    schedule_interval="0 6 * * *",  # expect: removed-dag-kwarg
    concurrency=4,  # expect: removed-dag-kwarg
    start_date=datetime(2026, 1, 1),
    catchup=False,
):
    PythonOperator(task_id="p", python_callable=print, provide_context=True)  # expect: removed-kwarg


@dag(timetable=CronDataIntervalTimetable("0 6 * * *", timezone="UTC"),  # expect: removed-dag-kwarg
     start_date=datetime(2026, 1, 1), catchup=False)
def legacy_decorated():
    pass


legacy_decorated()
