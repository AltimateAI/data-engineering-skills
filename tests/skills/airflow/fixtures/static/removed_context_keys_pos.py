# targets: 3.3
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, get_current_context, task


def legacy_callable(prev_execution_date, **kwargs):  # expect: removed-context-key
    print(kwargs["next_ds"])  # expect: removed-context-key
    return prev_execution_date


@task
def uses_context(execution_date=None):  # expect: removed-context-key
    ctx = get_current_context()
    a = ctx["yesterday_ds"]  # expect: removed-context-key
    b = ctx.get("tomorrow_ds")  # expect: removed-context-key
    c = get_current_context()["prev_ds_nodash"]  # expect: removed-context-key
    d = ctx["dag_run"].execution_date  # expect: removed-context-key
    return a, b, c, d


with DAG("removed_keys", schedule="@daily", start_date=datetime(2026, 1, 1), catchup=False):
    BashOperator(task_id="t1", bash_command="echo {{ execution_date }}")  # expect: removed-context-key
    BashOperator(task_id="t2", bash_command="run --from {{prev_ds}} --to {{ next_ds_nodash }}")  # expect: removed-context-key
    BashOperator(task_id="t3", bash_command="echo {{ dag_run.execution_date }}")  # expect: removed-context-key
    BashOperator(task_id="t4", bash_command="{% if yesterday_ds %}echo y{% endif %}")  # expect: removed-context-key
    PythonOperator(task_id="t5", python_callable=legacy_callable)
    uses_context()
