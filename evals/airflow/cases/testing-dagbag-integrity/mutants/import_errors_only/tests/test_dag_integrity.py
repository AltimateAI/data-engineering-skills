"""Checks that every DAG in dags/ loads."""

from __future__ import annotations

from pathlib import Path

from airflow.dag_processing.dagbag import DagBag

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"


def test_no_import_errors():
    bag = DagBag(dag_folder=str(DAGS_DIR))
    assert bag.import_errors == {}


def test_all_dags_present():
    bag = DagBag(dag_folder=str(DAGS_DIR))
    assert {"orders_ingest", "customer_snapshot", "marketing_spend"} <= set(bag.dag_ids)
    for dag in bag.dags.values():
        assert dag.tasks
