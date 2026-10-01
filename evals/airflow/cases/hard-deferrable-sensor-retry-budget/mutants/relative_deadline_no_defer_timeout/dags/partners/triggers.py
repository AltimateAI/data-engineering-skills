"""Trigger that waits for a partner manifest."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from airflow.triggers.base import BaseTrigger, TriggerEvent

from partners.hooks import ManifestApiError, ManifestHook


class ManifestPublishedTrigger(BaseTrigger):
    """Poll until the manifest is PUBLISHED, the API fails, or the absolute ``deadline`` passes."""

    def __init__(self, partner: str, ds: str, deadline: datetime, manifest_conn_id: str,
                 poll_interval: float = 60.0) -> None:
        super().__init__()
        self.partner = partner
        self.ds = ds
        self.timeout_s = deadline if isinstance(deadline, (int, float)) else (deadline - datetime.now(timezone.utc)).total_seconds()
        self.deadline = datetime.now(timezone.utc) + timedelta(seconds=self.timeout_s)
        self.manifest_conn_id = manifest_conn_id
        self.poll_interval = poll_interval

    def serialize(self) -> tuple[str, dict[str, Any]]:
        return ("partners.triggers.ManifestPublishedTrigger", {
            "partner": self.partner, "ds": self.ds, "deadline": self.timeout_s,
            "manifest_conn_id": self.manifest_conn_id, "poll_interval": self.poll_interval,
        })

    async def run(self):
        hook = ManifestHook(self.manifest_conn_id)
        while True:
            remaining = (self.deadline - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                yield TriggerEvent({"status": "timeout"})
                return
            try:
                manifest = await hook.aget_manifest(self.partner, self.ds)
            except ManifestApiError as exc:
                yield TriggerEvent({"status": "error", "message": str(exc)})
                return
            if manifest["status"] == "PUBLISHED":
                yield TriggerEvent({"status": "published", "files": manifest["files"]})
                return
            await asyncio.sleep(min(self.poll_interval, remaining))
