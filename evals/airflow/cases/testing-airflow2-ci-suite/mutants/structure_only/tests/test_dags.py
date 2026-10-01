"""CI tests for the Airflow 2.11 DAGs in dags/. No scheduler needed."""

from __future__ import annotations

from pathlib import Path

import pendulum
import pytest
from airflow.models import DagBag
from airflow.timetables.base import TimeRestriction

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAGS_DIR = PROJECT_ROOT / "dags"


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}, dagbag.import_errors
    assert {"shipments_daily", "carrier_rates_weekly"} <= set(dagbag.dag_ids)


def test_every_task_retries_at_least_twice(dagbag):
    low = [
        f"{dag_id}.{task.task_id}={task.retries}"
        for dag_id, dag in dagbag.dags.items()
        for task in dag.tasks
        if (task.retries or 0) < 2
    ]
    assert not low, low


def test_shipments_schedule_weekdays_0730_utc(dagbag):
    dag = dagbag.get_dag("shipments_daily")
    restriction = TimeRestriction(earliest=pendulum.datetime(2026, 3, 6, tz="UTC"), latest=None, catchup=True)
    runs, last = [], None
    for _ in range(10):
        info = dag.timetable.next_dagrun_info(last_automated_data_interval=last, restriction=restriction)
        runs.append(pendulum.instance(info.run_after).in_timezone("UTC"))
        last = info.data_interval
    assert all((r.hour, r.minute) == (7, 30) for r in runs), runs
    assert {r.isoweekday() for r in runs} == {1, 2, 3, 4, 5}, runs


def test_report_depends_on_extract(dagbag):
    dag = dagbag.get_dag("shipments_daily")
    assert "extract_shipments" in dag.get_task("build_report").upstream_task_ids
