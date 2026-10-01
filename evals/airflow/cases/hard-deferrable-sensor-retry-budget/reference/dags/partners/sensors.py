"""Sensor that waits for a partner's daily manifest."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from airflow.sdk import BaseSensorOperator, PokeReturnValue
from airflow.sdk.exceptions import AirflowSensorTimeout, AirflowSkipException

from partners.hooks import ManifestApiError, ManifestHook
from partners.triggers import ManifestPublishedTrigger

WAIT_STARTED_KEY = "manifest_wait_started_at"


class PartnerManifestSensor(BaseSensorOperator):
    """Wait until the partner has published the manifest for ``ds`` and return its file list.

    ``timeout`` is a budget per DAG run, counted from the first try's start. The start time
    lives in the task state store (Airflow 3.3), which keeps its rows across retries of the
    task instance; XComs are cleared when a task instance is retried.

    :param partner: partner key, e.g. ``acme``
    :param ds: manifest date (templated, usually ``{{ ds }}``)
    :param manifest_conn_id: connection to the manifest API
    :param deferrable: wait in the triggerer (default) instead of poking from a worker
    """

    template_fields: Sequence[str] = ("partner", "ds")

    def __init__(
        self,
        *,
        partner: str,
        ds: str = "{{ ds }}",
        manifest_conn_id: str = ManifestHook.default_conn_name,
        deferrable: bool = True,
        **kwargs: Any,
    ) -> None:
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

    def _gave_up(self):
        msg = f"{self.partner} manifest for {self.ds} not published within {self.timeout}s"
        if self.soft_fail:
            raise AirflowSkipException(msg)
        raise AirflowSensorTimeout(msg)

    def execute(self, context) -> Any:
        if not self.deferrable:
            return super().execute(context)
        store = context["task_state_store"]
        started = store.get(WAIT_STARTED_KEY)
        if started is None:
            started = datetime.now(timezone.utc).isoformat()
            store.set(WAIT_STARTED_KEY, started)
        deadline = datetime.fromisoformat(started) + timedelta(seconds=self.timeout)
        remaining = deadline - datetime.now(timezone.utc)
        if remaining <= timedelta(0):
            self._gave_up()
        self.defer(
            trigger=ManifestPublishedTrigger(partner=self.partner, ds=self.ds, deadline=deadline,
                                             manifest_conn_id=self.manifest_conn_id,
                                             poll_interval=self.poke_interval),
            method_name="execute_complete",
            timeout=remaining,
        )

    def execute_complete(self, context, event: dict[str, Any]) -> list[str]:
        if event["status"] == "published":
            return event["files"]
        if event["status"] == "timeout":
            self._gave_up()
        # Not an AirflowException: with soft_fail=True the sensor base class would turn it
        # into a skip, but an outage should use the task's retries.
        raise ManifestApiError(f"manifest API error for {self.partner}/{self.ds}: {event.get('message')}")
