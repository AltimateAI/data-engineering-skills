"""Sensor that waits for a partner's daily manifest."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from airflow.sdk import BaseSensorOperator, PokeReturnValue

from partners.hooks import ManifestHook


class PartnerManifestSensor(BaseSensorOperator):
    """Wait until the partner has published the manifest for ``ds`` and return its file list.

    :param partner: partner key, e.g. ``acme``
    :param ds: manifest date (templated, usually ``{{ ds }}``)
    :param manifest_conn_id: connection to the manifest API
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
        # MUTANT (adversarial no-op): flag accepted and stored, sensor still pokes from a worker.
        self.deferrable = deferrable

    def poke(self, context) -> PokeReturnValue | bool:
        manifest = ManifestHook(self.manifest_conn_id).get_manifest(self.partner, self.ds)
        if manifest["status"] == "PUBLISHED":
            return PokeReturnValue(is_done=True, xcom_value=manifest["files"])
        return False
