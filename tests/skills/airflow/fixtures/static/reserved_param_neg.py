# targets: 3.3 2.11
# near-miss: reserved-context-param
from datetime import datetime

from airflow import DAG
from airflow.decorators import task


@task
def extract():
    return "2026-01-01"


@task
def build_revenue(business_date: str, ds=None, ti=None):
    return business_date, ds, ti


def plain_helper(ds):
    return ds


with DAG("reserved_ok", schedule=None, start_date=datetime(2026, 1, 1), catchup=False):
    build_revenue(extract())
    build_revenue(business_date="2026-01-01")
    build_revenue(business_date="2026-01-01", ds="2026-01-01")  # keyword values work on both
    plain_helper("2026-01-01")
