"""Tests for dags/orders_enrichment.py. No scheduler needed; the end-to-end test uses dag.test()."""

from __future__ import annotations

import csv
import shutil
from datetime import datetime, timezone

import orders_enrichment as mod
import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk import DagRunState


@pytest.fixture(scope="module")
def dag():
    bag = DagBag(dag_folder=str(mod.PROJECT_ROOT / "dags"))
    assert bag.import_errors == {}
    return bag.dags["orders_enrichment"]


# --- transform logic: call the plain functions behind the @task decorators ---


def test_dedupe_keeps_latest_version_of_each_order():
    rows = [
        {"order_id": "B", "updated_at": "2026-03-02T08:00:00", "amount": "1"},
        {"order_id": "A", "updated_at": "2026-03-02T09:00:00", "amount": "old"},
        {"order_id": "A", "updated_at": "2026-03-02T10:00:00", "amount": "new"},
        {"order_id": "B", "updated_at": "2026-03-02T07:00:00", "amount": "older"},
    ]
    result = mod.dedupe_orders(rows)
    assert [(r["order_id"], r["amount"]) for r in result] == [("A", "new"), ("B", "1")]


def test_convert_to_usd_multiplies_and_rounds_half_up():
    rows = [
        {"order_id": "1", "currency": "EUR", "amount": "0.35"},
        {"order_id": "2", "currency": "USD", "amount": "9.99"},
        {"order_id": "3", "currency": "GBP", "amount": "10.00"},
    ]
    rates = {"USD": "1", "EUR": "1.0850", "GBP": "1.2700"}
    result = mod.convert_to_usd(rows, rates)
    assert [r["amount_usd"] for r in result] == ["0.38", "9.99", "12.70"]


def test_convert_to_usd_fails_on_unknown_currency():
    with pytest.raises(ValueError):
        mod.convert_to_usd([{"order_id": "1", "currency": "JPY", "amount": "5"}], {"USD": "1"})


# --- DAG wiring and schedule ---


def test_validate_runs_before_load(dag):
    assert "validate_totals" in dag.get_task("load_enriched").upstream_task_ids
    assert dag.get_task("convert_to_usd").upstream_task_ids == {"dedupe_orders", "load_fx_rates"}


def test_scheduled_daily_at_0600_utc(dag):
    assert dag.schedule == "0 6 * * *"
    assert dag.timezone.name == "UTC"


# --- end to end ---


def test_end_to_end_for_2026_03_02(dag):
    out_dir = mod.OUTPUT_DIR
    shutil.rmtree(out_dir, ignore_errors=True)
    dagrun = dag.test(logical_date=datetime(2026, 3, 2, 6, tzinfo=timezone.utc))
    assert dagrun.state == DagRunState.SUCCESS
    with (out_dir / "2026-03-02.csv").open(newline="") as fh:
        got = [(r["order_id"], r["amount"], r["amount_usd"]) for r in csv.DictReader(fh)]
    assert got == [
        ("S-102", "120.00", "130.20"),
        ("S-103", "40.50", "51.44"),
        ("S-104", "9.99", "9.99"),
        ("S-105", "0.35", "0.38"),
    ]
    shutil.rmtree(out_dir, ignore_errors=True)
