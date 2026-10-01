"""Operators that load files into the DuckDB warehouse."""

from __future__ import annotations

from typing import Any

from airflow.sdk import BaseOperator
from warehouse.hooks import DuckDBWarehouseHook


class CsvPartitionToDuckDBOperator(BaseOperator):
    """Load one date partition of a CSV export into a DuckDB table.

    The rows of ``csv_path`` whose ``partition_column`` equals ``partition_date``
    replace that partition in ``<connection schema>.<table>``, so re-runs and
    backfills are idempotent. All columns are loaded as text. Returns the number of
    rows loaded.
    """

    template_fields = ("csv_path", "partition_date")
    ui_color = "#fff3b0"

    def __init__(
        self,
        *,
        csv_path: str,
        table: str,
        partition_column: str,
        partition_date: str,
        duckdb_conn_id: str = DuckDBWarehouseHook.default_conn_name,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.csv_path = csv_path
        self.table = table
        self.partition_column = partition_column
        self.partition_date = partition_date
        self.duckdb_conn_id = duckdb_conn_id

    def execute(self, context) -> int:
        hook = DuckDBWarehouseHook(duckdb_conn_id=self.duckdb_conn_id)
        schema = hook.target_schema
        target = f'"{schema}"."{self.table}"'
        column = f'"{self.partition_column}"'
        source = "read_csv_auto(?, all_varchar = true)"
        con = hook.get_conn()
        try:
            con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            con.execute(f"CREATE TABLE IF NOT EXISTS {target} AS SELECT * FROM {source} LIMIT 0", [self.csv_path])
            con.execute("BEGIN TRANSACTION")
            con.execute(f"DELETE FROM {target} WHERE {column} = ?", [self.partition_date])
            con.execute(
                f"INSERT INTO {target} SELECT * FROM {source}",
                [self.csv_path],
            )
            loaded = con.execute(
                f"SELECT count(*) FROM {target} WHERE {column} = ?", [self.partition_date]
            ).fetchone()[0]
            con.execute("COMMIT")
        finally:
            con.close()
        self.log.info("Loaded %s rows into %s for %s", loaded, target, self.partition_date)
        return loaded
