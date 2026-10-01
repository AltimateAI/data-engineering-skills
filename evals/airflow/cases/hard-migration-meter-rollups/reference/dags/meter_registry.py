"""Daily export of the meter registry snapshot for the customer portal."""

from __future__ import annotations

import json

import pendulum
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, CronDataIntervalTimetable, Variable

from meter_lib.assets import PROJECT_ROOT, REGIONS

REGISTRY_DIR = PROJECT_ROOT / "output" / "registry"


def export_registry(**context):
    version = Variable.get("registry_version", default="2026.1")
    snapshot = {
        "as_of": context["logical_date"].isoformat(),
        "regions": REGIONS,
        "registry_version": version,
    }
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    (REGISTRY_DIR / f"{context['ds']}.json").write_text(json.dumps(snapshot, indent=2) + "\n")


with DAG(
    dag_id="meter_registry_daily",
    schedule=CronDataIntervalTimetable("@daily", timezone="UTC"),
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "metering"},
    tags=["metering", "portal"],
) as dag:
    PythonOperator(task_id="export_registry", python_callable=export_registry)
