# targets: 3.3 2.11
# near-miss: top-level-io
from datetime import datetime

try:
    from airflow.sdk import Variable, dag, task
    from airflow.providers.standard.operators.python import PythonOperator
except ImportError:
    from airflow.decorators import dag, task
    from airflow.models import Variable
    from airflow.operators.python import PythonOperator


def landing_dir():
    return Variable.get("landing_dir")


def export(**context):
    return Variable.get("export_target")


@task
def resolve():
    return landing_dir()


def unused_helper():
    return Variable.get("never_called_at_parse")


@dag(schedule=None, start_date=datetime(2026, 1, 1), catchup=False)
def decorated():
    @task
    def load(path: str):
        return f"{landing_dir()}/{path}"

    def not_called():
        return Variable.get("nested_but_never_called")

    PythonOperator(task_id="export", python_callable=export)
    load(resolve())
    later = lambda: Variable.get("lazy")  # noqa: E731, F841


decorated()
