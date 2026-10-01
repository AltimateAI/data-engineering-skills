"""Hook for the clearing-house export drop (connection ``claims_export``)."""

from __future__ import annotations

import csv
from pathlib import Path

from airflow.hooks.base import BaseHook


class ClaimsExportHook(BaseHook):
    """Reads the CSV exports from the directory in the connection's ``export_dir`` extra."""

    conn_name_attr = "claims_export_conn_id"
    default_conn_name = "claims_export"
    conn_type = "fs"
    hook_name = "Claims export drop"

    def __init__(self, claims_export_conn_id: str = default_conn_name) -> None:
        super().__init__()
        self.claims_export_conn_id = claims_export_conn_id

    def export_dir(self) -> Path:
        conn = self.get_connection(self.claims_export_conn_id)
        return Path(conn.extra_dejson["export_dir"])

    def read(self, name: str) -> list[dict[str, str]]:
        with (self.export_dir() / name).open(newline="") as fh:
            return list(csv.DictReader(fh))
