# targets: 2.11
from datetime import datetime

from airflow import DAG
from airflow.decorators import task


@task
def extract():
    return "2026-01-01"


@task
def build_revenue(ds: str):
    return ds


with DAG("reserved_positional", schedule=None, start_date=datetime(2026, 1, 1), catchup=False):
    build_revenue(extract())  # expect: reserved-context-param
    build_revenue(ds="2026-01-01")
