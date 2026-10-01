# targets: 3.3
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, task


@task
def consume(**context):
    ti = context["ti"]
    rows = ti.xcom_pull()  # expect: xcom-pull-no-task-ids
    path = ti.xcom_pull(key="output_path")  # expect: xcom-pull-no-task-ids
    return rows, path


with DAG("xcom_pos", schedule=None, start_date=datetime(2026, 1, 1), catchup=False):
    BashOperator(task_id="report", bash_command="echo {{ ti.xcom_pull() }}")  # expect: xcom-pull-no-task-ids
    consume()
