"""Sensor that waits for a lake partition, deferring to the triggerer."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from airflow.sdk import BaseSensorOperator, PokeReturnValue, Variable
from airflow.sdk.exceptions import AirflowException, AirflowSensorTimeout, AirflowSkipException

from lake.hooks import LakeCatalogHook
from lake.triggers import PartitionPublishedTrigger


class PartitionPublishedSensor(BaseSensorOperator):
    """Wait until ``table``/``partition`` is PUBLISHED and return its file list."""

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
        ti = context["ti"]
        key = f"lake_wait_start__{ti.dag_id}__{ti.run_id}__{ti.task_id}__{ti.map_index}"
        started = Variable.get(key, default=None)
        if started is None:
            started = datetime.now(timezone.utc).isoformat()
            Variable.set(key, started)
        left = datetime.fromisoformat(started) + timedelta(seconds=self.timeout) - datetime.now(timezone.utc)
        if left <= timedelta(0):
            raise (AirflowSkipException if self.soft_fail else AirflowSensorTimeout)("wait budget used up")
        self.defer(
            trigger=PartitionPublishedTrigger(table=self.table, partition=self.partition,
                                              lake_conn_id=self.lake_conn_id, poll_interval=self.poke_interval),
            method_name="execute_complete",
            # the scheduler fails the deferral at this absolute time, restart or not;
            # BaseSensorOperator turns that into AirflowSensorTimeout (soft_fail -> skipped)
            timeout=left,
        )

    def execute_complete(self, context, event: dict[str, Any]) -> list[str]:
        if event["status"] == "published":
            return event["files"]
        if event["status"] == "timeout":
            raise AirflowSensorTimeout(f"{self.table}/{self.partition} not published in time")
        raise AirflowException(f"catalog API error for {self.table}/{self.partition}: {event.get('message')}")
