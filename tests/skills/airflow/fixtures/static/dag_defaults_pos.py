# targets: 3.3 2.11
from datetime import datetime

from airflow import DAG
from airflow.decorators import dag

with DAG("no_schedule", start_date=datetime(2026, 1, 1)):  # expect: schedule-missing
    pass

with DAG("implicit_catchup", schedule="@daily", start_date=datetime(2026, 1, 1)):  # expect: catchup-implicit
    pass


@dag  # expect: schedule-missing
def bare_decorator():
    pass


bare_decorator()
