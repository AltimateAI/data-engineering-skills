"""Sensor that waits for a partner's daily manifest (alt: Variable anchor, scheduler-enforced timeout)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from airflow.sdk import BaseSensorOperator, PokeReturnValue, Variable
from airflow.sdk.exceptions import AirflowSensorTimeout
from airflow.triggers.base import BaseTrigger, TriggerEvent

from partners.hooks import ManifestHook


class ManifestApiDown(RuntimeError):
    """Raised on resume after an API error so the task's retries apply (never a skip)."""


class ManifestTrigger(BaseTrigger):
    def __init__(self, partner: str, ds: str, conn_id: str, interval: float) -> None:
        super().__init__()
        self.partner, self.ds, self.conn_id, self.interval = partner, ds, conn_id, interval

    def serialize(self):
        return ("partners.sensors.ManifestTrigger",
                {"partner": self.partner, "ds": self.ds, "conn_id": self.conn_id, "interval": self.interval})

    async def run(self):
        hook = ManifestHook(self.conn_id)
        while True:
            try:
                m = await asyncio.to_thread(hook.get_manifest, self.partner, self.ds)
            except Exception as exc:  # noqa: BLE001
                yield TriggerEvent({"ok": False, "error": str(exc)})
                return
            if m["status"] == "PUBLISHED":
                yield TriggerEvent({"ok": True, "files": m["files"]})
                return
            await asyncio.sleep(self.interval)


class PartnerManifestSensor(BaseSensorOperator):
    """Wait until the partner has published the manifest for ``ds`` and return its file list."""

    template_fields: Sequence[str] = ("partner", "ds")

    def __init__(self, *, partner: str, ds: str = "{{ ds }}",
                 manifest_conn_id: str = ManifestHook.default_conn_name, deferrable: bool = True,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.partner = partner
        self.ds = ds
        self.manifest_conn_id = manifest_conn_id
        self.deferrable = deferrable

    def poke(self, context) -> PokeReturnValue | bool:
        manifest = ManifestHook(self.manifest_conn_id).get_manifest(self.partner, self.ds)
        if manifest["status"] == "PUBLISHED":
            return PokeReturnValue(is_done=True, xcom_value=manifest["files"])
        return False

    def execute(self, context) -> Any:
        if not self.deferrable:
            return super().execute(context)
        ti = context["ti"]
        key = f"manifest_wait_start__{ti.dag_id}__{ti.run_id}__{ti.task_id}__{ti.map_index}"
        started = Variable.get(key, default=None)
        if started is None:
            started = datetime.now(timezone.utc).isoformat()
            Variable.set(key, started)
        left = datetime.fromisoformat(started) + timedelta(seconds=self.timeout) - datetime.now(timezone.utc)
        if left <= timedelta(0):
            # resume_execution is not involved here, so honour soft_fail ourselves
            from airflow.sdk.exceptions import AirflowSkipException

            raise (AirflowSkipException if self.soft_fail else AirflowSensorTimeout)("manifest wait budget used up")
        self.defer(trigger=ManifestTrigger(self.partner, self.ds, self.manifest_conn_id, self.poke_interval),
                   method_name="done", timeout=left)

    def done(self, context, event):
        if event["ok"]:
            return event["files"]
        raise ManifestApiDown(event["error"])
