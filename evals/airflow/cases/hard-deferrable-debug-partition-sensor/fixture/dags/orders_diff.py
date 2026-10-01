"""Day-over-day diff of the orders partition."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import dag, task

from lake.sensors import PartitionPublishedSensor


@dag(
    schedule="0 6 * * *",
    start_date=datetime(2026, 9, 1),
    catchup=False,
    default_args={"retries": 3, "retry_delay": timedelta(minutes=5)},
    tags=["lake"],
)
def orders_diff():
    today = PartitionPublishedSensor(task_id="wait_today", table="orders", partition="{{ ds }}",
                                     poke_interval=120, timeout=2 * 3600)
    yesterday = PartitionPublishedSensor(task_id="wait_yesterday", table="orders",
                                         partition="{{ macros.ds_add(ds, -1) }}", poke_interval=120, timeout=2 * 3600)

    @task
    def diff(today_files: list[str], yesterday_files: list[str]):
        added = sorted(set(today_files) - set(yesterday_files))
        print(f"{len(added)} new files")
        return added

    diff(today.output, yesterday.output)


orders_diff()
