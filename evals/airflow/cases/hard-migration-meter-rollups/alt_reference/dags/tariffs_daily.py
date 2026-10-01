"""Daily tariff sync from the utility's price sheet (data/tariffs.csv)."""

from __future__ import annotations

from pathlib import Path

import pendulum
from airflow.sdk import CronDataIntervalTimetable, dag, get_current_context, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dag(
    schedule=CronDataIntervalTimetable("0 1 * * *", timezone="UTC"),
    start_date=pendulum.datetime(2026, 3, 3, tz="UTC"),
    catchup=True,
    max_active_runs=1,
    default_args={"owner": "metering", "retries": 1},
    tags=["metering", "reference-data"],
)
def tariffs_daily():
    @task
    def sync_tariffs() -> list[str]:
        dr = get_current_context()["dag_run"]
        # scheduled: the interval's day; CLI trigger (no logical date on Airflow 3): today
        first = pendulum.instance(dr.logical_date or dr.run_after).in_tz("UTC").date()
        days = [first.isoformat(), first.add(days=1).isoformat()]
        dest = PROJECT_ROOT / "output" / "lake" / "tariffs"
        dest.mkdir(parents=True, exist_ok=True)
        lines = (PROJECT_ROOT / "data" / "tariffs.csv").read_text().splitlines()
        for day in days:
            (dest / f"{day}.csv").write_text("".join(line + "\n" for line in lines if line.startswith(day + ",")))
        return days

    sync_tariffs()


tariffs_daily()
