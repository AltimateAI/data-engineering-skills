# targets: 3.3 2.11
# near-miss: sensor-poke-no-timeout
from datetime import datetime

from airflow import DAG
from airflow.decorators import task
from airflow.providers.standard.sensors.external_task import ExternalTaskSensor
from airflow.providers.standard.sensors.filesystem import FileSensor
from airflow.sensors.base import BaseSensorOperator


class ReadyFlagSensor(BaseSensorOperator):
    def poke(self, context):
        return True


@task.sensor(poke_interval=60, timeout=3600, mode="reschedule")
def partner_file_ready():
    return True


with DAG("sensors_neg", schedule="@daily", start_date=datetime(2026, 1, 1), catchup=False):
    FileSensor(task_id="wait_file", filepath="/data/in/ready.flag", timeout=2 * 3600)
    FileSensor(task_id="wait_file_resched", filepath="/data/in/b.flag", mode="reschedule")
    ExternalTaskSensor(task_id="wait_up", external_dag_id="upstream", deferrable=True)
    ReadyFlagSensor(task_id="custom", timeout=600, poke_interval=30)
    partner_file_ready()
