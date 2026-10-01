"""Hook for the partner manifest API.

GET /v1/partners/<partner>/manifests/<ds>
  200 {"status": "PENDING"} or {"status": "PUBLISHED", "files": ["s3://...", ...]}
  anything else is an error
"""

from __future__ import annotations

import httpx
import requests
from airflow.sdk import BaseHook


class ManifestApiError(Exception):
    """The manifest API answered with an error or could not be reached."""


class ManifestHook(BaseHook):
    """Connection: ``host``/``port`` locate the API, ``schema`` is the URL scheme, ``password`` the token."""

    conn_name_attr = "manifest_conn_id"
    default_conn_name = "manifests_default"
    conn_type = "http"
    hook_name = "Partner manifests"

    def __init__(self, manifest_conn_id: str = default_conn_name, request_timeout: float = 20.0) -> None:
        super().__init__()
        self.manifest_conn_id = manifest_conn_id
        self.request_timeout = request_timeout

    @staticmethod
    def url_and_headers(conn, partner: str, ds: str) -> tuple[str, dict[str, str]]:
        port = f":{conn.port}" if conn.port else ""
        url = f"{conn.schema or 'http'}://{conn.host}{port}/v1/partners/{partner}/manifests/{ds}"
        return url, {"Authorization": f"Bearer {conn.password}"}

    def get_manifest(self, partner: str, ds: str) -> dict:
        url, headers = self.url_and_headers(self.get_connection(self.manifest_conn_id), partner, ds)
        try:
            resp = requests.get(url, headers=headers, timeout=self.request_timeout)
        except requests.RequestException as exc:
            raise ManifestApiError(f"GET {url} failed: {exc!r}") from exc
        if resp.status_code != 200:
            raise ManifestApiError(f"GET {url} -> HTTP {resp.status_code}")
        return resp.json()

    async def aget_manifest(self, partner: str, ds: str) -> dict:
        """Async variant for triggers."""
        url, headers = self.url_and_headers(await self.aget_connection(self.manifest_conn_id), partner, ds)
        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                resp = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise ManifestApiError(f"GET {url} failed: {exc!r}") from exc
        if resp.status_code != 200:
            raise ManifestApiError(f"GET {url} -> HTTP {resp.status_code}")
        return resp.json()
