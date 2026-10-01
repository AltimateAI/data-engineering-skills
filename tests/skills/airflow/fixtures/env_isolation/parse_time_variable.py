from datetime import datetime

from airflow import DAG
from airflow.models import Variable

# Parse-time lookup: must never reach a real metadata DB when checked.
TARGET = Variable.get("fixture_target_path", default_var="/tmp/out")

with DAG("reads_variable_at_parse", schedule=None, start_date=datetime(2026, 1, 1), catchup=False):
    pass
