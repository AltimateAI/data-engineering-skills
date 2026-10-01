# targets: 3.3
# near-miss: sdk-import-on-2x
from datetime import datetime

from airflow.sdk import dag, task


@dag(schedule=None, start_date=datetime(2026, 1, 1), catchup=False)
def uses_sdk():
    @task
    def hello():
        return 1

    hello()


uses_sdk()
