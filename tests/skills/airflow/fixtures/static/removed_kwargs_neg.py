# targets: 3.3
# near-miss: removed-dag-kwarg, removed-kwarg
from datetime import datetime

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, CronDataIntervalTimetable, dag

with DAG(
    "modern_kwargs",
    schedule="0 6 * * *",
    max_active_tasks=4,
    start_date=datetime(2026, 1, 1),
    catchup=False,
):
    PythonOperator(task_id="p", python_callable=print)


@dag(schedule=CronDataIntervalTimetable("0 6 * * *", timezone="UTC"),
     start_date=datetime(2026, 1, 1), catchup=False)
def modern_decorated():
    pass


modern_decorated()
