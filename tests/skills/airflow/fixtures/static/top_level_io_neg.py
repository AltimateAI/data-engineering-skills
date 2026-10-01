# targets: 3.3 2.11
# near-miss: top-level-io
from datetime import datetime

import requests
from airflow import DAG
from airflow.decorators import task
from airflow.hooks.base import BaseHook
from airflow.models import Variable

CONFIG = {"bucket": "{{ var.value.landing_bucket }}"}


def helper():
    return Variable.get("landing_bucket")


@task
def fetch():
    conn = BaseHook.get_connection("warehouse")
    return requests.get(conn.host, timeout=10).status_code


fallback = lambda: Variable.get("x")  # noqa: E731

with DAG("parse_io_ok", schedule=None, start_date=datetime(2026, 1, 1), catchup=False) as dag:
    fetch()

if __name__ == "__main__":
    print(Variable.get("debug_only"))
    dag.test()
