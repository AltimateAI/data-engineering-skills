"""Hook for the data-lake catalog API.

GET /v1/tables/<table>/partitions/<partition>
  200 {"state": "PENDING"} or {"state": "PUBLISHED", "files": ["s3://...", ...]}
  anything else is an error
"""

from __future__ import annotations

import httpx
import requests
from airflow.sdk import BaseHook


class LakeApiError(Exception):
    """The catalog API answered with an error or could not be reached."""


class LakeCatalogHook(BaseHook):
    """Connection: ``host``/``port`` locate the API, ``schema`` is the URL scheme, ``password`` the token."""

    conn_name_attr = "lake_conn_id"
    default_conn_name = "lake_default"
    conn_type = "http"
    hook_name = "Lake catalog"

    def __init__(self, lake_conn_id: str = default_conn_name, request_timeout: float = 20.0) -> None:
        super().__init__()
        self.lake_conn_id = lake_conn_id
        self.request_timeout = request_timeout

    @staticmethod
    def _url_and_headers(conn, table: str, partition: str) -> tuple[str, dict[str, str]]:
        port = f":{conn.port}" if conn.port else ""
        url = f"{conn.schema or 'http'}://{conn.host}{port}/v1/tables/{table}/partitions/{partition}"
        return url, {"Authorization": f"Bearer {conn.password}"}

    def _fetch(self, url: str, headers: dict[str, str]) -> dict:
        try:
            resp = requests.get(url, headers=headers, timeout=self.request_timeout)
        except requests.RequestException as exc:
            raise LakeApiError(f"GET {url} failed: {exc!r}") from exc
        if resp.status_code != 200:
            raise LakeApiError(f"GET {url} -> HTTP {resp.status_code}")
        return resp.json()

    def get_partition(self, table: str, partition: str) -> dict:
        url, headers = self._url_and_headers(self.get_connection(self.lake_conn_id), table, partition)
        return self._fetch(url, headers)

    async def aget_partition(self, table: str, partition: str) -> dict:
        """Async variant for triggers."""
        conn = await self.aget_connection(self.lake_conn_id)
        url, headers = self._url_and_headers(conn, table, partition)
        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                resp = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise LakeApiError(f"GET {url} failed: {exc!r}") from exc
        if resp.status_code != 200:
            raise LakeApiError(f"GET {url} -> HTTP {resp.status_code}")
        return resp.json()
