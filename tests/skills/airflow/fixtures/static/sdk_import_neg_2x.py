# targets: 2.11
# near-miss: sdk-import-on-2x
from datetime import datetime

from airflow.decorators import dag, task

try:  # version shim: the 2.x fallback below is what runs here
    from airflow.sdk import Asset
except ImportError:
    from airflow.datasets import Dataset as Asset


@dag(schedule=[Asset("s3://bucket/orders")], start_date=datetime(2026, 1, 1), catchup=False)
def uses_decorators():
    @task
    def hello():
        return 1

    hello()


uses_decorators()
