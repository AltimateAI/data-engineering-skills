# targets: 3.3
from datetime import datetime

from airflow import settings
from airflow.models import DagRun
from airflow.sdk import DAG, task
from airflow.utils.session import create_session


@task
def last_success(**context):
    with create_session() as session:  # expect: db-access-in-task
        runs = session.query(DagRun).filter(DagRun.dag_id == "x").all()  # expect: db-access-in-task
    previous = DagRun.find(dag_id="x")  # expect: db-access-in-task
    s = settings.Session()  # expect: db-access-in-task
    return runs, previous, s


with DAG("db_access", schedule=None, start_date=datetime(2026, 1, 1), catchup=False):
    last_success()
