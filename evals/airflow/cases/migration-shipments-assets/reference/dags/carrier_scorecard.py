"""Carrier on-time scorecard, rebuilt whenever a new shipments batch lands."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Asset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = PROJECT_ROOT / "output" / "warehouse" / "shipments"
SCORECARD_DIR = PROJECT_ROOT / "output" / "scorecard"
SHIPMENTS = Asset("warehouse://shipments/batches")


def build_scorecard(ti, **_):
    latest: dict[str, dict] = {}
    for batch in sorted(BATCH_DIR.glob("batch_*.csv")):
        with batch.open(newline="") as fh:
            for row in csv.DictReader(fh):
                seen = latest.get(row["shipment_id"])
                if seen is None or (row["updated_at"], row["event_id"]) > (seen["updated_at"], seen["event_id"]):
                    latest[row["shipment_id"]] = row

    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # shipments, delivered, on time
    for row in latest.values():
        s = stats[row["carrier"]]
        s[0] += 1
        if row["status"] == "delivered":
            s[1] += 1
            if row["updated_at"][:10] <= row["promised_date"]:
                s[2] += 1

    SCORECARD_DIR.mkdir(parents=True, exist_ok=True)
    with (SCORECARD_DIR / "carrier_scorecard.csv").open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["carrier", "shipments", "delivered", "on_time", "on_time_rate"])
        for carrier in sorted(stats):
            shipments, delivered, on_time = stats[carrier]
            rate = f"{on_time / delivered:.3f}" if delivered else ""
            writer.writerow([carrier, shipments, delivered, on_time, rate])
    ti.xcom_push(key="carriers", value=len(stats))
    ti.xcom_push(key="shipments", value=len(latest))


with DAG(
    dag_id="carrier_scorecard",
    schedule=[SHIPMENTS],
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "logistics-data"},
    params={"scorecard_dir": str(SCORECARD_DIR)},
    tags=["logistics", "reporting"],
) as dag:
    build = PythonOperator(task_id="build_scorecard", python_callable=build_scorecard)
    mark_ready = BashOperator(
        task_id="mark_ready",
        bash_command=(
            "echo 'carriers={{ ti.xcom_pull(task_ids=\"build_scorecard\", key=\"carriers\") }} "
            "shipments={{ ti.xcom_pull(task_ids=\"build_scorecard\", key=\"shipments\") }}' "
            "> {{ params.scorecard_dir }}/_READY"
        ),
    )
    build >> mark_ready
