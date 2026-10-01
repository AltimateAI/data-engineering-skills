"""CI checks: every DAG imports and the revenue pipeline keeps its shape."""

import os
from pathlib import Path

from airflow.models import DagBag

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")


def _bag():
    return DagBag(dag_folder=str(DAGS_DIR))


def test_no_import_errors():
    assert _bag().import_errors == {}


def test_daily_revenue_structure():
    dag = _bag().dags["daily_revenue"]
    assert set(dag.task_ids) == {"load_daily_revenue", "publish_manifest"}
    assert dag.get_task("publish_manifest").upstream_task_ids == {"load_daily_revenue"}
