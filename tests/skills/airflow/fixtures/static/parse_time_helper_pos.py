# targets: 3.3 2.11
from datetime import datetime

import requests

try:
    from airflow.sdk import DAG, Variable, dag, task
except ImportError:
    from airflow import DAG
    from airflow.decorators import dag, task
    from airflow.models import Variable


def landing_dir():
    return Variable.get("landing_dir", default="/tmp/landing")  # expect: top-level-io


def settings():
    return {"dir": landing_dir(), "region": fetch_region()}


def fetch_region():
    return requests.get("https://config.internal/region").text  # expect: top-level-io


@dag(schedule=None, start_date=datetime(2026, 1, 1), catchup=False)
def decorated():
    bucket = Variable.get("bucket")  # expect: top-level-io

    @task
    def load(path: str):
        return path

    load(f"{bucket}/{settings()['dir']}")


decorated()


def make_dag(name):
    with DAG(name, schedule=None, start_date=datetime(2026, 1, 1), catchup=False) as d:
        Variable.get(f"{name}_threshold")  # expect: top-level-io
    return d


factory_dag = make_dag("factory")
