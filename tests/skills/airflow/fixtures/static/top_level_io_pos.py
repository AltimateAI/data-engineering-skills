# targets: 3.3 2.11
from datetime import datetime

import requests
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.models import Variable
from airflow.providers.postgres.hooks.postgres import PostgresHook

BUCKET = Variable.get("landing_bucket")  # expect: top-level-io
CONN = BaseHook.get_connection("warehouse")  # expect: top-level-io
TABLES = requests.get("https://config.internal/tables.json").json()  # expect: top-level-io
PARTNERS = PostgresHook("warehouse").get_records("select id from partners")  # expect: top-level-io


class Settings:
    region = Variable.get("region", default_var="us")  # expect: top-level-io


def build(path=Variable.get("default_path")):  # expect: top-level-io
    return path


with DAG("parse_io", schedule=None, start_date=datetime(2026, 1, 1), catchup=False):
    for partner_id, in PARTNERS:
        threshold = Variable.get(f"threshold_{partner_id}")  # expect: top-level-io


if __name__ != "__main__":
    WAREHOUSE = Variable.get("warehouse")  # expect: top-level-io
