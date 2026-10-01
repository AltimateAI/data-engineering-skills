"""DAG integrity and policy checks for every DAG in dags/. Runs without a scheduler."""

from __future__ import annotations

from pathlib import Path

import pytest
from airflow.models import DagBag

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"
EXPECTED_DAGS = {"orders_ingest", "customer_snapshot", "marketing_spend"}


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}, "\n".join(
        f"{path}:\n{err}" for path, err in dagbag.import_errors.items()
    )


def test_expected_dags_loaded(dagbag):
    assert EXPECTED_DAGS <= set(dagbag.dag_ids)


def test_every_dag_follows_policy(dagbag):
    assert dagbag.dags, "no DAGs parsed"
    problems = []
    for dag_id, dag in dagbag.dags.items():
        if not dag.tags:
            problems.append(f"{dag_id}: no tags")
        if dag.catchup:
            problems.append(f"{dag_id}: catchup is enabled")
        for task in dag.tasks:
            if not task.owner or task.owner == "airflow":
                problems.append(f"{dag_id}.{task.task_id}: owner not set")
            if (task.retries or 0) < 2:
                problems.append(f"{dag_id}.{task.task_id}: retries={task.retries}")
    assert not problems, problems


def test_orders_ingest_shape(dagbag):
    dag = dagbag.dags["orders_ingest"]
    chain = ["extract_orders", "validate_orders", "load_orders", "publish_summary"]
    assert set(dag.task_ids) == set(chain)
    for upstream, downstream in zip(chain, chain[1:]):
        assert dag.get_task(downstream).upstream_task_ids == {upstream}
    assert dag.get_task("extract_orders").upstream_task_ids == set()
