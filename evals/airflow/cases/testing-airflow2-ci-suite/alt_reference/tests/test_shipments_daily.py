import csv
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from airflow.models import DagBag

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "dags"))
shipments = importlib.import_module("shipments_daily")

BAG = DagBag(str(REPO / "dags"), include_examples=False)


def test_dagbag_loads_cleanly():
    assert not BAG.import_errors, BAG.import_errors
    assert len(BAG.dags) >= 2


@pytest.mark.parametrize("dag_id", ["shipments_daily", "carrier_rates_weekly"])
def test_retry_policy(dag_id):
    dag = BAG.get_dag(dag_id)
    assert dag is not None
    for task in dag.tasks:
        assert task.retries >= 2, f"{task.task_id} has retries={task.retries}"


def test_schedule_is_weekdays_at_0730_utc():
    dag = BAG.get_dag("shipments_daily")
    assert dag.schedule_interval == "30 7 * * 1-5"
    assert str(dag.timezone.name) == "UTC"


def test_extract_feeds_report():
    dag = BAG.get_dag("shipments_daily")
    assert dag.get_task("extract_shipments").downstream_task_ids == {"build_report"}


SAMPLE = [
    # id, ship, promised, delivered, expected days_late (None = not late) as of 2026-03-10
    ("late_today", "2026-03-01", "2026-03-08", "2026-03-10", 2),
    ("open_overdue", "2026-03-01", "2026-03-09", "", 1),
    ("open_due_today", "2026-03-01", "2026-03-10", "", None),
    ("on_time_today", "2026-03-01", "2026-03-10", "2026-03-10", None),
    ("late_yesterday", "2026-03-01", "2026-03-05", "2026-03-09", None),
    ("future_ship", "2026-03-11", "2026-03-09", "", None),
]


@pytest.mark.parametrize("sid,ship,promised,delivered,expected", SAMPLE, ids=[s[0] for s in SAMPLE])
def test_late_rules(sid, ship, promised, delivered, expected):
    row = {"shipment_id": sid, "ship_date": ship, "carrier": "UPS",
           "promised_date": promised, "delivered_date": delivered}
    result = shipments.find_late_shipments([row], "2026-03-10")
    if expected is None:
        assert result == []
    else:
        assert len(result) == 1 and result[0]["days_late"] == expected


def test_airflow_dags_test_cli(tmp_path):
    report = REPO / "output" / "late_shipments" / "2026-03-03.csv"
    if report.exists():
        report.unlink()
    env = dict(os.environ, AIRFLOW__CORE__DAGS_FOLDER=str(REPO / "dags"))
    proc = subprocess.run(
        [sys.executable, "-m", "airflow", "dags", "test", "shipments_daily", "2026-03-03"],
        env=env, capture_output=True, text=True, timeout=240,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    with report.open(newline="") as fh:
        rows = {r["shipment_id"]: int(r["days_late"]) for r in csv.DictReader(fh)}
    assert rows == {"SH-1009": 5, "SH-1003": 3, "SH-1007": 2, "SH-1001": 1}
