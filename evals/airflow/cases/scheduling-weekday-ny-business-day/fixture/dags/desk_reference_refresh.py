"""Weekly copy of the desk reference list used by the reporting DAGs."""

import shutil
from pathlib import Path

import pendulum
from airflow.sdk import dag, task

PROJECT_DIR = Path(__file__).resolve().parents[1]


@dag(
    dag_id="desk_reference_refresh",
    schedule="@weekly",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "treasury-data"},
    tags=["treasury", "reference"],
)
def desk_reference_refresh():
    @task
    def copy_desks() -> str:
        target = PROJECT_DIR / "reports" / "reference" / "desks.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_DIR / "data" / "desks.csv", target)
        return str(target)

    copy_desks()


desk_reference_refresh()
