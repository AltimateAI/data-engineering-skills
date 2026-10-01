# targets: 3.3 2.11
from datetime import datetime

from airflow import DAG
from airflow.decorators import task
from airflow.providers.standard.sensors.external_task import ExternalTaskSensor
from airflow.providers.standard.sensors.filesystem import FileSensor


@task.sensor(poke_interval=60)  # expect: sensor-poke-no-timeout
def partner_file_ready():
    return False


with DAG("sensors_pos", schedule="@daily", start_date=datetime(2026, 1, 1), catchup=False):
    FileSensor(task_id="wait_file", filepath="/data/in/ready.flag")  # expect: sensor-poke-no-timeout
    ExternalTaskSensor(task_id="wait_up", external_dag_id="upstream", mode="poke")  # expect: sensor-poke-no-timeout
    partner_file_ready()
