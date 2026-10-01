"""Trigger that waits for a lake partition to be published (alt fix: no trigger-side deadline)."""

from __future__ import annotations

import asyncio
from typing import Any

from airflow.triggers.base import BaseTrigger, TriggerEvent

from lake.hooks import LakeApiError, LakeCatalogHook

# Published partitions never change, so remember them and spare the catalog API.
_PUBLISHED: dict[tuple[str, str], dict] = {}


class PartitionPublishedTrigger(BaseTrigger):
    """Poll the catalog until the partition is PUBLISHED or the API fails.

    The sensor's timeout is enforced by the scheduler through ``defer(timeout=...)``;
    ``timeout`` is kept for compatibility with stored trigger rows.
    """

    def __init__(
        self,
        table: str,
        partition: str,
        timeout: float | None = None,
        lake_conn_id: str = LakeCatalogHook.default_conn_name,
        poll_interval: float = 60.0,
    ) -> None:
        super().__init__()
        self.table = table
        self.partition = partition
        self.timeout = timeout
        self.lake_conn_id = lake_conn_id
        self.poll_interval = poll_interval

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
        key = (self.table, self.partition)
        hook = LakeCatalogHook(self.lake_conn_id)
        while key not in _PUBLISHED:
            try:
                info = await asyncio.to_thread(hook.get_partition, self.table, self.partition)
            except LakeApiError as exc:
                yield TriggerEvent({"status": "error", "message": str(exc)})
                return
            if info["state"] == "PUBLISHED":
                _PUBLISHED[key] = info
                break
            await asyncio.sleep(self.poll_interval)
        yield TriggerEvent({"status": "published", "files": _PUBLISHED[key]["files"]})
