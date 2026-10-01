# targets: 3.3
# near-miss: removed-context-key
"""Docstrings may mention {{ execution_date }} without being templates."""
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, task


def helper(execution_date):
    # Not a task callable: an ordinary helper argument.
    return execution_date


@task
def reads_rows(rows=None, **context):
    record = {"execution_date": "2026-01-01"}
    value = record["execution_date"]
    day = context["logical_date"]
    return value, day, helper("x")


with DAG("modern_keys", schedule="@daily", start_date=datetime(2026, 1, 1), catchup=False):
    BashOperator(task_id="t1", bash_command="echo {{ ds }} {{ macros.ds_add(ds, -1) }}")
    BashOperator(task_id="t2", bash_command="echo {{ params.execution_date }}")
    BashOperator(task_id="t3", bash_command="echo execution_date prev_ds")
    BashOperator(task_id="t4", bash_command="echo {{ dag_run.logical_date }} {{ data_interval_start }}")
    reads_rows()
