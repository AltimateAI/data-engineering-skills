"""Weekly average freight rate per carrier, for the procurement dashboard."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output" / "carrier_rates"


def summarize_rates(ds: str, **context) -> str:
    totals: dict[str, list[float]] = defaultdict(list)
    with (DATA_DIR / "carrier_rates.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            totals[row["carrier"]].append(float(row["rate_per_kg"]))
    out = OUTPUT_DIR / f"{ds}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["carrier", "avg_rate_per_kg"])
        for carrier in sorted(totals):
            writer.writerow([carrier, f"{sum(totals[carrier]) / len(totals[carrier]):.3f}"])
    return str(out)


with DAG(
    dag_id="carrier_rates_weekly",
    schedule="0 9 * * 1",
    start_date=datetime(2026, 1, 5),
    catchup=False,
    default_args={"owner": "logistics-data", "retries": 2, "retry_delay": timedelta(minutes=30)},
    tags=["logistics", "procurement"],
) as dag:
    PythonOperator(task_id="summarize_rates", python_callable=summarize_rates)
