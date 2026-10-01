# targets: 3.3
from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG


def notify(*args):
    print(args)


default_args = {
    "owner": "data",
    "sla": timedelta(hours=1),  # expect: sla-ignored
}

with DAG(
    "sla_on_3x",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    sla_miss_callback=notify,  # expect: sla-ignored
):
    BashOperator(task_id="load", bash_command="echo load", sla=timedelta(hours=2))  # expect: sla-ignored
