"""CI tests for the Airflow 2.11 DAGs in dags/. No scheduler needed."""

from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

import pendulum
import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.timetables.base import TimeRestriction
from airflow.sdk import DagRunState

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAGS_DIR = PROJECT_ROOT / "dags"
sys.path.insert(0, str(DAGS_DIR))

import shipments_daily  # noqa: E402


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR))


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


def _row(sid, promised, delivered="", shipped="2026-02-20"):
    return {"shipment_id": sid, "ship_date": shipped, "carrier": "DHL",
            "promised_date": promised, "delivered_date": delivered}


def test_delivered_late_on_run_date():
    late = shipments_daily.find_late_shipments([_row("A", "2026-03-01", "2026-03-03")], "2026-03-03")
    assert [(r["shipment_id"], r["days_late"]) for r in late] == [("A", 2)]


def test_on_time_early_and_other_days_are_not_late():
    rows = [
        _row("on_time", "2026-03-03", "2026-03-03"),
        _row("early", "2026-03-04", "2026-03-03"),
        _row("late_other_day", "2026-02-24", "2026-03-02"),
        _row("due_today_open", "2026-03-03"),
        _row("not_shipped", "2026-03-01", shipped="2026-03-04"),
    ]
    assert shipments_daily.find_late_shipments(rows, "2026-03-03") == []


def test_undelivered_past_promise_is_late():
    late = shipments_daily.find_late_shipments([_row("B", "2026-02-26")], "2026-03-03")
    assert [(r["shipment_id"], r["days_late"]) for r in late] == [("B", 5)]


def test_end_to_end_2026_03_03(dagbag):
    out_dir = shipments_daily.OUTPUT_DIR
    shutil.rmtree(out_dir, ignore_errors=True)
    dag = dagbag.get_dag("shipments_daily")
    dagrun = dag.test(logical_date=pendulum.datetime(2026, 3, 3, 7, 30, tz="UTC"))
    assert dagrun.state == DagRunState.SUCCESS
    with (out_dir / "2026-03-03.csv").open(newline="") as fh:
        got = [(r["shipment_id"], r["days_late"]) for r in csv.DictReader(fh)]
    assert got == [("SH-1009", "5"), ("SH-1003", "3"), ("SH-1007", "2"), ("SH-1001", "1")]
    shutil.rmtree(out_dir, ignore_errors=True)
