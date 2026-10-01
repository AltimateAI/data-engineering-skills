# targets: 2.11
from datetime import datetime

from airflow.sdk import dag, task  # expect: sdk-import-on-2x
import airflow.sdk.definitions.asset  # expect: sdk-import-on-2x


@dag(schedule=None, start_date=datetime(2026, 1, 1), catchup=False)
def uses_sdk():
    @task
    def hello():
        return 1

    hello()


uses_sdk()
