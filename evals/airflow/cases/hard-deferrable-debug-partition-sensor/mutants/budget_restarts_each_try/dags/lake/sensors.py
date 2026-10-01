"""Sensor that waits for a lake partition, deferring to the triggerer."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from airflow.sdk import BaseSensorOperator, PokeReturnValue
from airflow.sdk.exceptions import AirflowException, AirflowSensorTimeout, AirflowSkipException

from lake.hooks import LakeCatalogHook
from lake.triggers import PartitionPublishedTrigger


class PartitionPublishedSensor(BaseSensorOperator):
    """Wait until ``table``/``partition`` is PUBLISHED and return its file list.

    :param table: catalog table name
    :param partition: partition key (templated)
    :param lake_conn_id: connection to the catalog API
    :param deferrable: wait in the triggerer (default) instead of poking from a worker
    """

    template_fields: Sequence[str] = ("table", "partition")

    def __init__(
        self,
        *,
        table: str,
        partition: str = "{{ ds }}",
        lake_conn_id: str = LakeCatalogHook.default_conn_name,
        deferrable: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.table = table
        self.partition = partition
        self.lake_conn_id = lake_conn_id
        self.deferrable = deferrable

    def poke(self, context) -> PokeReturnValue | bool:
        info = LakeCatalogHook(self.lake_conn_id).get_partition(self.table, self.partition)
        if info["state"] == "PUBLISHED":
            return PokeReturnValue(is_done=True, xcom_value=info["files"])
        return False

    def execute(self, context) -> Any:
        if not self.deferrable:
            return super().execute(context)
        # The timeout is a budget per DAG run: remember when the first try started waiting.
        # The task state store keeps its rows across retries (XComs are cleared on retry).
        started = datetime.now(timezone.utc).isoformat()
        deadline = datetime.fromisoformat(started) + timedelta(seconds=self.timeout)
        remaining = deadline - datetime.now(timezone.utc)
        if remaining <= timedelta(0):
            msg = f"{self.table}/{self.partition} was not published within {self.timeout}s"
            raise AirflowSkipException(msg) if self.soft_fail else AirflowSensorTimeout(msg)
        self.defer(
            trigger=PartitionPublishedTrigger(
                table=self.table,
                partition=self.partition,
                deadline=deadline,
                lake_conn_id=self.lake_conn_id,
                poll_interval=self.poke_interval,
            ),
            method_name="execute_complete",
            timeout=remaining,
        )

    def execute_complete(self, context, event: dict[str, Any]) -> list[str]:
        status = event["status"]
        if status == "timeout":
            raise AirflowSensorTimeout(f"{self.table}/{self.partition} was not published within {self.timeout}s")
        if status != "published":
            raise AirflowException(f"catalog API error for {self.table}/{self.partition}: {event.get('message')}")
        files = event["files"]
        self.log.info("%s/%s published with %d files", self.table, self.partition, len(files))
        return files
