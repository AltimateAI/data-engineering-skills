# targets: 3.3 2.11
from datetime import datetime

from airflow import DAG
from airflow.decorators import task


@task
def extract():
    return "2026-01-01"


@task
def build_revenue(ds: str):
    return ds


@task
def per_partition(params, run_id=None):
    return params, run_id


with DAG("reserved_params", schedule=None, start_date=datetime(2026, 1, 1), catchup=False):
    per_partition.expand(params=[{"a": 1}, {"a": 2}])  # expect: reserved-context-param
    build_revenue.partial(ds="2026-01-01").expand(x=[1])  # expect: reserved-context-param
