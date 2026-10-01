"""Daily order feed for our partner ACME.

For each day: extract ACME's orders, write a manifest next to them, then copy
both into the outbox that the partner's SFTP sync picks up.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORDERS_CSV = PROJECT_ROOT / "data" / "partner_orders.csv"
FEED_DIR = PROJECT_ROOT / "output" / "partner_feed"
OUTBOX = PROJECT_ROOT / "outbox" / "acme"
FEED_COLUMNS = ["order_id", "sku", "qty", "amount"]


def feed_day(context) -> str:
    """Day (YYYY-MM-DD) this run produces the feed for.

    Scheduled runs use their logical date. Manual runs triggered without a
    logical date have no `logical_date`/`ds` in the context; they use the time
    the run was triggered for, so clearing the run later reproduces the same day.
    """
    dag_run = context["dag_run"]
    when = dag_run.logical_date or dag_run.run_after
    return when.strftime("%Y-%m-%d")


@dag(
    schedule="0 4 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["partner", "acme"],
)
def partner_feed():
    @task
    def extract_orders(**context) -> str:
        day = feed_day(context)
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
    def write_manifest(feed_path: str, **context) -> str:
        day = feed_day(context)
        with open(feed_path, newline="") as fh:
            row_count = sum(1 for _ in csv.DictReader(fh))
        manifest = Path(feed_path).with_name("manifest.json")
        manifest.write_text(
            json.dumps({"partner": "acme", "partition": day, "row_count": row_count}, indent=2)
        )
        return str(manifest)

    deliver = BashOperator(
        task_id="deliver",
        bash_command=(
            "mkdir -p {{ params.outbox }}"
            " && cp {{ ti.xcom_pull(task_ids='extract_orders') }}"
            " {{ params.outbox }}/acme_orders_{{ (dag_run.logical_date or dag_run.run_after) | ds_nodash }}.csv"
            " && cp {{ ti.xcom_pull(task_ids='write_manifest') }}"
            " {{ params.outbox }}/acme_orders_{{ (dag_run.logical_date or dag_run.run_after) | ds_nodash }}.manifest.json"
        ),
        params={"outbox": str(OUTBOX)},
    )

    write_manifest(extract_orders()) >> deliver


partner_feed()
