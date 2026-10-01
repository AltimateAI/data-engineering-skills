"""Structural tests for orders_enrichment."""

from __future__ import annotations

from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"


@pytest.fixture(scope="module")
def dag():
    bag = DagBag(dag_folder=str(DAGS_DIR))
    assert bag.import_errors == {}
    return bag.dags["orders_enrichment"]


def test_tasks_present(dag):
    assert set(dag.task_ids) == {
        "extract_orders", "load_fx_rates", "dedupe_orders",
        "convert_to_usd", "validate_totals", "load_enriched",
    }


def test_validate_before_load(dag):
    assert "validate_totals" in dag.get_task("load_enriched").upstream_task_ids


def test_schedule(dag):
    assert dag.schedule == "0 6 * * *"
    assert dag.catchup is False
