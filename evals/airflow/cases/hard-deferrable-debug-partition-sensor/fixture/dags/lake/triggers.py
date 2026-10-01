"""Trigger that waits for a lake partition to be published."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from airflow.triggers.base import BaseTrigger, TaskSuccessEvent, TriggerEvent

from lake.hooks import LakeApiError, LakeCatalogHook

# Published partitions never change, so remember them and spare the catalog API.
_PUBLISHED: dict[str, dict] = {}


class PartitionPublishedTrigger(BaseTrigger):
    """Poll the catalog until the partition is PUBLISHED, the API fails, or ``timeout`` seconds pass."""

    def __init__(
        self,
        table: str,
        partition: str,
        timeout: float,
        lake_conn_id: str = LakeCatalogHook.default_conn_name,
        poll_interval: float = 60.0,
    ) -> None:
        super().__init__()
        self.table = table
        self.partition = partition
        self.timeout = timeout
        self.lake_conn_id = lake_conn_id
        self.poll_interval = poll_interval
        self.give_up_at = time.monotonic() + timeout

    def serialize(self) -> tuple[str, dict[str, Any]]:
        return (
            "lake.triggers.PartitionPublishedTrigger",
            {
                "table": self.table,
                "partition": self.partition,
                "timeout": self.timeout,
                "lake_conn_id": self.lake_conn_id,
                "poll_interval": self.poll_interval,
            },
        )

    async def run(self):
        hook = LakeCatalogHook(self.lake_conn_id)
        while True:
            if self.table in _PUBLISHED:
                # Finish the task right here: no worker slot is needed just to return the list.
                yield TaskSuccessEvent(xcoms={"return_value": _PUBLISHED[self.table]["files"]})
                return
            if time.monotonic() >= self.give_up_at:
                yield TriggerEvent({"status": "timeout"})
                return
            try:
                info = await hook.aget_partition(self.table, self.partition)
            except LakeApiError as exc:
                yield TriggerEvent({"status": "error", "message": str(exc)})
                return
            if info["state"] == "PUBLISHED":
                _PUBLISHED[self.table] = info
                continue
            await asyncio.sleep(self.poll_interval)
