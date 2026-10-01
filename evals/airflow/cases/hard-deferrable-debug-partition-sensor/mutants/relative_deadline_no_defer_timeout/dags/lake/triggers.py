"""Trigger that waits for a lake partition to be published."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from airflow.triggers.base import BaseTrigger, TriggerEvent

from lake.hooks import LakeApiError, LakeCatalogHook


class PartitionPublishedTrigger(BaseTrigger):
    """Poll the catalog until the partition is PUBLISHED, the API fails, or ``deadline`` passes.

    ``deadline`` is an absolute UTC datetime so a trigger rebuilt after a triggerer restart
    keeps it.
    """

    def __init__(
        self,
        table: str,
        partition: str,
        deadline: datetime,
        lake_conn_id: str = LakeCatalogHook.default_conn_name,
        poll_interval: float = 60.0,
    ) -> None:
        super().__init__()
        self.table = table
        self.partition = partition
        self.deadline = deadline
        self.timeout_s = deadline if isinstance(deadline, (int, float)) else (deadline - datetime.now(timezone.utc)).total_seconds()
        self._give_up_at = time.monotonic() + self.timeout_s
        self.lake_conn_id = lake_conn_id
        self.poll_interval = poll_interval

    def serialize(self) -> tuple[str, dict[str, Any]]:
        return (
            "lake.triggers.PartitionPublishedTrigger",
            {
                "table": self.table,
                "partition": self.partition,
                "deadline": self.timeout_s,
                "lake_conn_id": self.lake_conn_id,
                "poll_interval": self.poll_interval,
            },
        )

    async def run(self):
        hook = LakeCatalogHook(self.lake_conn_id)
        while True:
            remaining = self._give_up_at - time.monotonic()
            if remaining <= 0:
                yield TriggerEvent({"status": "timeout"})
                return
            try:
                info = await hook.aget_partition(self.table, self.partition)
            except LakeApiError as exc:
                yield TriggerEvent({"status": "error", "message": str(exc)})
                return
            if info["state"] == "PUBLISHED":
                yield TriggerEvent({"status": "published", "files": info["files"]})
                return
            await asyncio.sleep(min(self.poll_interval, remaining))
