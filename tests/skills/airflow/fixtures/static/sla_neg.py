# targets: 3.3
# near-miss: sla-ignored
from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

default_args = {"owner": "data", "execution_timeout": timedelta(hours=1)}
report_config = {"sla": "gold", "tier": 1}

with DAG(
    "no_sla",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    params={"sla": "gold"},
):
    BashOperator(task_id="load", bash_command="echo load", execution_timeout=timedelta(hours=2))
