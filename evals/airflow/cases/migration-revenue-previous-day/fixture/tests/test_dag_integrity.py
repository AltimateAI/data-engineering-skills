"""CI checks: every DAG imports and the revenue pipeline keeps its shape."""

from pathlib import Path

import pytest
from airflow.models import DagBag

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"


@pytest.fixture(scope="session")
def dagbag():
    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}


def test_daily_revenue_structure(dagbag):
    dag = dagbag.get_dag("daily_revenue")
    assert dag is not None
    assert set(dag.task_ids) == {"load_daily_revenue", "publish_manifest"}
    assert dag.get_task("publish_manifest").upstream_task_ids == {"load_daily_revenue"}
