# targets: 3.3 2.11
# near-miss: xcom-pull-no-task-ids
from datetime import datetime

from airflow import DAG

try:
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:
    from airflow.operators.bash import BashOperator


def consume(ti=None):
    rows = ti.xcom_pull(task_ids="extract")
    path = ti.xcom_pull("extract", key="output_path")
    both = ti.xcom_pull(task_ids=["a", "b"], key="count")
    return rows, path, both


with DAG("xcom_neg", schedule=None, start_date=datetime(2026, 1, 1), catchup=False):
    BashOperator(task_id="report", bash_command="echo {{ ti.xcom_pull(task_ids='extract') }}")
