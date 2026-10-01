"""Daily revenue per region.

Runs every morning at 04:15 UTC, once the late order events for the previous
business day (UTC) have landed, and writes one CSV per business day plus a
small manifest the finance dashboard polls for.
"""

from __future__ import annotations

import csv
from datetime import timedelta
from pathlib import Path

import duckdb
import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, CronDataIntervalTimetable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORDERS_PATH = PROJECT_ROOT / "data" / "orders.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"

default_args = {
    "owner": "finance-data",
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}


def run_revenue_query(templates_dict, ds, **_):
    """Run the rendered query and overwrite the CSV for the business day."""
    rows = duckdb.sql(templates_dict["query"]).fetchall()
    out = OUTPUT_DIR / "daily_revenue" / f"{ds}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["region", "orders", "revenue"])
        for region, orders, revenue in rows:
            writer.writerow([region, orders, f"{revenue:.2f}"])
    return str(out)


with DAG(
    dag_id="daily_revenue",
    # Airflow 3 maps a bare cron string to CronTriggerTimetable (logical date =
    # the tick). Keep the Airflow 2 data-interval semantics: the 04:15 run on day
    # D covers [D-1 04:15, D 04:15) and its ``ds`` is the business day D-1.
    schedule=CronDataIntervalTimetable("15 4 * * *", timezone="UTC"),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    template_searchpath=[str(Path(__file__).parent / "sql")],
    params={"orders_path": str(ORDERS_PATH), "output_dir": str(OUTPUT_DIR)},
    tags=["finance", "revenue"],
) as dag:
    load_daily_revenue = PythonOperator(
        task_id="load_daily_revenue",
        python_callable=run_revenue_query,
        templates_dict={"query": "daily_revenue.sql"},
        templates_exts=[".sql"],
    )

    publish_manifest = BashOperator(
        task_id="publish_manifest",
        bash_command=(
            "mkdir -p {{ params.output_dir }}/manifests && "
            "echo '{\"business_date\": \"{{ ds }}\", \"logical_ts\": \"{{ logical_date }}\"}' "
            "> {{ params.output_dir }}/manifests/{{ ds }}.json"
        ),
    )

    load_daily_revenue >> publish_manifest
