from datetime import datetime

from airflow import DAG

import module_that_does_not_exist_anywhere  # noqa: F401

with DAG("broken", schedule=None, start_date=datetime(2026, 1, 1), catchup=False):
    pass
