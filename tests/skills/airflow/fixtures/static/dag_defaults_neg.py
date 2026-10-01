# targets: 3.3 2.11
# near-miss: schedule-missing, catchup-implicit
from datetime import datetime

from airflow import DAG
from airflow.decorators import dag

COMMON = {"start_date": datetime(2026, 1, 1), "schedule": "@daily", "catchup": True}

with DAG("explicit", schedule="@daily", start_date=datetime(2026, 1, 1), catchup=True):
    pass

with DAG("manual_only", schedule=None, start_date=datetime(2026, 1, 1)):
    pass

with DAG("from_kwargs", **COMMON):
    pass


@dag(schedule="@hourly", start_date=datetime(2026, 1, 1), catchup=False)
def decorated():
    pass


decorated()
