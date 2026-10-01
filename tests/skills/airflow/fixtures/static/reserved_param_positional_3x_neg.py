# targets: 3.3
# near-miss: reserved-context-param
# A positional or keyword value for a context-named parameter works on Airflow 3.x (checked on 3.3).
from datetime import datetime

from airflow.sdk import DAG, task


@task
def extract():
    return "2026-01-01"


@task
def build_revenue(ds: str):
    return ds


with DAG("reserved_positional_3x", schedule=None, start_date=datetime(2026, 1, 1), catchup=False):
    build_revenue(extract())
    build_revenue(ds="2026-01-01")
