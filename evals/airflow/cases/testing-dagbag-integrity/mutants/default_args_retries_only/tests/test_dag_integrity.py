"""DAG integrity and policy checks for every DAG in dags/. Runs without a scheduler."""

from __future__ import annotations

from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"
EXPECTED_DAGS = {"orders_ingest", "customer_snapshot", "marketing_spend"}


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    # Airflow 3.x: DagBag lives in airflow.dag_processing.dagbag and has no
    # include_examples argument (examples are controlled by core.load_examples).
    return DagBag(dag_folder=str(DAGS_DIR))


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
        args = dag.default_args or {}
        if args.get("owner", "airflow") == "airflow":
            problems.append(f"{dag_id}: owner not set")
        if args.get("retries", 0) < 2:
            problems.append(f"{dag_id}: retries={args.get('retries')}")
    assert not problems, problems


def test_orders_ingest_shape(dagbag):
    dag = dagbag.dags["orders_ingest"]
    chain = ["extract_orders", "validate_orders", "load_orders", "publish_summary"]
    assert set(dag.task_ids) == set(chain)
    for upstream, downstream in zip(chain, chain[1:]):
        assert dag.get_task(downstream).upstream_task_ids == {upstream}
    assert dag.get_task("extract_orders").upstream_task_ids == set()
