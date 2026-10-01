"""Daily ingest of lake partitions into the warehouse."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import dag, task

from lake.sensors import PartitionPublishedSensor


@dag(
    schedule="0 5 * * *",
    start_date=datetime(2026, 9, 1),
    catchup=False,
    default_args={"retries": 3, "retry_delay": timedelta(minutes=5)},
    tags=["lake"],
)
def lake_ingest():
    orders = PartitionPublishedSensor(task_id="wait_orders", table="orders", poke_interval=120, timeout=2 * 3600)
    # customers is best effort: skip the load when the partition is late
    customers = PartitionPublishedSensor(
        task_id="wait_customers", table="customers", poke_interval=120, timeout=2 * 3600, soft_fail=True
    )

    @task
    def load(table: str, files: list[str]):
        print(f"loading {len(files)} files into {table}")
        return len(files)

    load.override(task_id="load_orders")("orders", orders.output)
    load.override(task_id="load_customers")("customers", customers.output)


lake_ingest()
