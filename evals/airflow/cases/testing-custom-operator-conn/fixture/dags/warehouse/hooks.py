"""Hook for the DuckDB warehouse file."""

from __future__ import annotations

from typing import Any

from airflow.sdk import BaseHook


class DuckDBWarehouseHook(BaseHook):
    """Opens the DuckDB database configured on an Airflow connection.

    Connection fields:
      host   - path to the .duckdb file (required)
      schema - schema that tables are written to (default ``main``)
      extra  - ``{"read_only": true}`` opens the file read-only
    """

    conn_name_attr = "duckdb_conn_id"
    default_conn_name = "duckdb_warehouse"
    conn_type = "duckdb"
    hook_name = "DuckDB warehouse"

    def __init__(self, duckdb_conn_id: str = default_conn_name, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.duckdb_conn_id = duckdb_conn_id
        self._connection = None

    @property
    def connection(self):
        if self._connection is None:
            self._connection = self.get_connection(self.duckdb_conn_id)
        return self._connection

    @property
    def database_path(self) -> str:
        path = self.connection.host
        if not path:
            raise ValueError(
                f"Connection {self.duckdb_conn_id!r} has no host; set it to the DuckDB file path"
            )
        return path

    @property
    def target_schema(self) -> str:
        return self.connection.schema or "main"

    def get_conn(self):
        import duckdb

        read_only = bool(self.connection.extra_dejson.get("read_only", False))
        return duckdb.connect(self.database_path, read_only=read_only)
