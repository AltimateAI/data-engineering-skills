"""Daily order feed for our partner ACME.

For each day: extract ACME's orders, write a manifest next to them, then copy
both into the outbox that the partner's SFTP sync picks up.

The feed day is resolved once, in `resolve_day`, and passed downstream. Manual
runs triggered without a logical date use the date they were triggered for.
"""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, get_current_context, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORDERS_CSV = PROJECT_ROOT / "data" / "partner_orders.csv"
FEED_DIR = PROJECT_ROOT / "output" / "partner_feed"
OUTBOX = PROJECT_ROOT / "outbox" / "acme"
FEED_COLUMNS = ["order_id", "sku", "qty", "amount"]


@dag(
    schedule="0 4 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["partner", "acme"],
)
def partner_feed():
    @task
    def resolve_day() -> str:
        context = get_current_context()
        logical_date = context.get("logical_date")
        if logical_date is not None:
            return logical_date.date().isoformat()
        return context["dag_run"].run_after.date().isoformat()

    @task
    def extract_orders(day: str) -> str:
        with ORDERS_CSV.open(newline="") as fh:
            rows = [
                {col: row[col] for col in FEED_COLUMNS}
                for row in csv.DictReader(fh)
                if row["order_date"] == day and row["partner"] == "acme"
            ]
        out = FEED_DIR / day / "orders.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FEED_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return str(out)

    @task
    def write_manifest(feed_path: str, day: str) -> str:
        with open(feed_path, newline="") as fh:
            row_count = sum(1 for _ in csv.DictReader(fh))
        manifest = Path(feed_path).with_name("manifest.json")
        manifest.write_text(
            json.dumps({"partner": "acme", "partition": day, "row_count": row_count}, indent=2)
        )
        return str(manifest)

    @task
    def deliver(feed_path: str, manifest_path: str, day: str) -> None:
        OUTBOX.mkdir(parents=True, exist_ok=True)
        stamp = day.replace("-", "")
        shutil.copyfile(feed_path, OUTBOX / f"acme_orders_{stamp}.csv")
        shutil.copyfile(manifest_path, OUTBOX / f"acme_orders_{stamp}.manifest.json")

    day = resolve_day()
    feed = extract_orders(day)
    manifest = write_manifest(feed, day)
    deliver(feed, manifest, day)


partner_feed()
