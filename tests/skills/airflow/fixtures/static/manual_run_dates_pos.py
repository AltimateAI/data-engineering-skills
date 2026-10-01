# targets: 3.3
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

with DAG("uses_run_dates", schedule="@daily", start_date=datetime(2026, 1, 1), catchup=False):
    BashOperator(task_id="export", bash_command="export --day {{ ds }}")  # expect: manual-run-dates
    BashOperator(task_id="again", bash_command="export --day {{ ds_nodash }}")
