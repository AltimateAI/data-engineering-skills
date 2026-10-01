# targets: 2.11
# near-miss: removed-context-key, manual-run-dates
# Airflow 2.x still provides these keys: no removed-key errors on a 2.x target.
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG("legacy_keys", schedule="@daily", start_date=datetime(2026, 1, 1), catchup=False):
    BashOperator(task_id="t1", bash_command="echo {{ execution_date }} {{ prev_ds }} {{ ds }}")
    BashOperator(task_id="t2", bash_command="echo {{ ti.xcom_pull() }}")
