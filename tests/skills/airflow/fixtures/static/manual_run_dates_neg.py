# targets: 3.3
# near-miss: manual-run-dates
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

with DAG("uses_run_after", schedule="@daily", start_date=datetime(2026, 1, 1), catchup=False):
    BashOperator(task_id="export", bash_command="export --day {{ dag_run.run_after | ds }}")
    BashOperator(task_id="param", bash_command="export --day {{ params.day }}")
