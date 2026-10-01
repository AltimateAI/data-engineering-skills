import csv
import importlib.util
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from airflow.models import DagBag
from airflow.timetables.base import TimeRestriction
from airflow.timetables.trigger import CronTriggerTimetable

ROOT = Path(__file__).resolve().parent.parent
DAG_FILE = ROOT / "dags" / "orders_enrichment.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("orders_enrichment_under_test", DAG_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


enrichment = _load_module()


@pytest.fixture(scope="module")
def dag():
    bag = DagBag(dag_folder=str(ROOT / "dags"))
    assert not bag.import_errors
    return bag.get_dag("orders_enrichment")


@pytest.mark.parametrize(
    "amount,rate,expected",
    [("0.35", "1.0850", "0.38"), ("40.50", "1.2700", "51.44"), ("10.00", "1", "10.00"), ("1.005", "1", "1.01")],
)
def test_usd_rounding_half_up(amount, rate, expected):
    rows = [{"order_id": "X", "currency": "EUR", "amount": amount}]
    (out,) = enrichment.convert_to_usd.function(rows, {"USD": "1", "EUR": rate})
    assert out["amount_usd"] == expected


def test_missing_rate_raises():
    with pytest.raises(ValueError, match="CHF"):
        enrichment.convert_to_usd.function(
            [{"order_id": "X", "currency": "CHF", "amount": "1.00"}], {"USD": "1"}
        )


def test_latest_version_wins_regardless_of_file_order():
    early = {"order_id": "O1", "updated_at": "2026-03-02T01:00:00", "amount": "1"}
    late = {"order_id": "O1", "updated_at": "2026-03-02T23:00:00", "amount": "2"}
    assert enrichment.dedupe_orders.function([early, late]) == [late]
    assert enrichment.dedupe_orders.function([late, early]) == [late]


def test_negative_amount_is_rejected():
    with pytest.raises(ValueError):
        enrichment.validate_totals.function([{"order_id": "X", "customer_id": "C", "amount_usd": "-1.00"}])


def test_nothing_published_before_validation(dag):
    assert dag.get_task("load_enriched").upstream_task_ids == {"validate_totals"}
    assert dag.get_task("validate_totals").upstream_task_ids == {"convert_to_usd"}


def test_next_run_is_0600_utc(dag):
    timetable = CronTriggerTimetable(dag.schedule, timezone="UTC")
    info = timetable.next_dagrun_info(
        last_automated_data_interval=None,
        restriction=TimeRestriction(earliest=datetime(2026, 3, 2, tzinfo=timezone.utc), latest=None, catchup=True),
    )
    assert info.run_after == datetime(2026, 3, 2, 6, tzinfo=timezone.utc)
    later = timetable.next_dagrun_info(
        last_automated_data_interval=info.data_interval,
        restriction=TimeRestriction(earliest=None, latest=None, catchup=True),
    )
    assert later.run_after == datetime(2026, 3, 3, 6, tzinfo=timezone.utc)


def test_sample_day_pipeline(tmp_path, monkeypatch):
    """Run the task functions in DAG order on the sample data for 2026-03-02."""
    monkeypatch.setattr(enrichment, "OUTPUT_DIR", tmp_path)
    ds = "2026-03-02"
    orders = enrichment.dedupe_orders.function(enrichment.extract_orders.function(ds=ds))
    enriched = enrichment.convert_to_usd.function(orders, enrichment.load_fx_rates.function(ds=ds))
    path = enrichment.load_enriched.function(enrichment.validate_totals.function(enriched), ds=ds)
    with open(path, newline="") as fh:
        got = {r["order_id"]: Decimal(r["amount_usd"]) for r in csv.DictReader(fh)}
    assert got == {
        "S-102": Decimal("130.20"),
        "S-103": Decimal("51.44"),
        "S-104": Decimal("9.99"),
        "S-105": Decimal("0.38"),
    }
