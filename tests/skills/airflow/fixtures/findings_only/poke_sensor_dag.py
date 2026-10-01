from datetime import datetime

from airflow import DAG

try:
    from airflow.providers.standard.sensors.filesystem import FileSensor
except ImportError:
    from airflow.sensors.filesystem import FileSensor

with DAG(
    "waits_for_file",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
):
    FileSensor(task_id="wait_for_drop", filepath="/data/incoming/ready.flag")
