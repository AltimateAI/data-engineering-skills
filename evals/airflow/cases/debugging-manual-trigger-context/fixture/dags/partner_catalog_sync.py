"""Weekly list of SKUs we have sold to ACME, for their catalogue team."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dag(
    schedule="0 6 * * 1",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["partner", "acme"],
)
def partner_catalog_sync():
    @task
    def export_skus() -> str:
        with (PROJECT_ROOT / "data" / "partner_orders.csv").open(newline="") as fh:
            skus = sorted({r["sku"] for r in csv.DictReader(fh) if r["partner"] == "acme"})
        out = PROJECT_ROOT / "output" / "partner_catalog" / "acme_skus.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(skus) + "\n")
        return str(out)

    export_skus()


partner_catalog_sync()
