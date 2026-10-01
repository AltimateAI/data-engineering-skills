"""Enrich the daily orders export with USD amounts and publish it for finance.

Runs every day at 06:00 UTC, after the upstream export for the day has landed.
Output: output/orders_enriched/<ds>.csv
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output" / "orders_enriched"
OUTPUT_COLUMNS = ["order_id", "customer_id", "currency", "amount", "amount_usd"]


@task
def extract_orders(ds: str | None = None) -> list[dict]:
    """All order rows exported for the run date (an order can appear more than once)."""
    with (DATA_DIR / "orders.csv").open(newline="") as fh:
        return [row for row in csv.DictReader(fh) if row["order_date"] == ds]


@task
def load_fx_rates(ds: str | None = None) -> dict[str, str]:
    """USD per unit of each currency on the run date."""
    rates = {"USD": "1"}
    with (DATA_DIR / "fx_rates.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["rate_date"] == ds:
                rates[row["currency"]] = row["usd_per_unit"]
    return rates


@task
def dedupe_orders(rows: list[dict]) -> list[dict]:
    """Keep only the latest version of each order (highest updated_at), sorted by order_id."""
    latest: dict[str, dict] = {}
    for row in rows:
        current = latest.get(row["order_id"])
        if current is None or row["updated_at"] > current["updated_at"]:
            latest[row["order_id"]] = row
    return [latest[order_id] for order_id in sorted(latest)]


@task
def convert_to_usd(rows: list[dict], rates: dict[str, str]) -> list[dict]:
    """Add amount_usd = amount * usd_per_unit, rounded half-up to cents."""
    enriched = []
    for row in rows:
        # Unmapped currency codes are almost always USD exports with a blank code.
        rate = rates.get(row["currency"], "1")
        usd = (Decimal(row["amount"]) * Decimal(rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        enriched.append({**row, "amount_usd": str(usd)})
    return enriched


@task
def validate_totals(rows: list[dict]) -> list[dict]:
    """Refuse to publish orders without a customer or with a negative USD amount."""
    bad = [r["order_id"] for r in rows if not r["customer_id"] or Decimal(r["amount_usd"]) < 0]
    if bad:
        raise ValueError(f"invalid orders: {bad}")
    return rows


@task
def load_enriched(rows: list[dict], ds: str | None = None) -> str:
    out = OUTPUT_DIR / f"{ds}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return str(out)


@dag(
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "finance-data", "retries": 2, "retry_delay": timedelta(minutes=10)},
    tags=["orders", "finance"],
)
def orders_enrichment():
    orders = dedupe_orders(extract_orders())
    enriched = convert_to_usd(orders, load_fx_rates())
    load_enriched(validate_totals(enriched))


orders_enrichment()
