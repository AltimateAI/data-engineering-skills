"""Daily sales rollup per store.

Convention for this repo: every daily DAG writes one file per logical date
(`{{ ds }}`) under output/<dag_id>/, so a rerun simply overwrites that day.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.decorators import dag, task
from airflow.operators.empty import EmptyOperator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"


@dag(
    dag_id="sales_daily",
    schedule="15 1 * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "supply-chain-analytics", "retries": 1, "retry_delay": timedelta(minutes=10)},
    tags=["sales"],
)
def sales_daily():
    start = EmptyOperator(task_id="start")

    @task
    def rollup(ds=None) -> str:
        totals: dict[str, float] = defaultdict(float)
        with (DATA_DIR / "sales.csv").open(newline="") as fh:
            for row in csv.DictReader(fh):
                if row["sale_date"] == ds:
                    totals[row["store_id"]] += float(row["amount"])
        out = OUTPUT_DIR / "sales_daily" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["store_id", "revenue"])
            for store in sorted(totals):
                writer.writerow([store, round(totals[store], 2)])
        return str(out)

    start >> rollup()


sales_daily()
