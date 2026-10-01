"""Daily revenue per store for the previous UTC calendar day (classic operator, templated date)."""

from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

ROOT = Path(__file__).resolve().parents[1]


def build_report(report_day: str) -> str:
    orders: Counter[str] = Counter()
    revenue: dict[str, Decimal] = {}
    with open(ROOT / "data" / "orders.csv", newline="") as fh:
        for row in csv.DictReader(fh):
            if pendulum.parse(row["order_ts"], tz="UTC").to_date_string() != report_day:
                continue
            orders[row["store_id"]] += 1
            revenue[row["store_id"]] = revenue.get(row["store_id"], Decimal(0)) + Decimal(row["amount"])
    out = ROOT / "output" / "daily_revenue" / f"{report_day}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["store_id", "orders", "revenue"])
        for store in sorted(orders):
            w.writerow([store, orders[store], str(revenue[store].quantize(Decimal("0.01")))])
    return str(out)


with DAG(
    dag_id="daily_revenue",
    schedule="0 3 * * *",  # 3.x: CronTriggerTimetable, logical date == trigger time
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
):
    PythonOperator(
        task_id="build_report",
        python_callable=build_report,
        op_kwargs={"report_day": pendulum.now("UTC").subtract(days=1).to_date_string()},
    )
