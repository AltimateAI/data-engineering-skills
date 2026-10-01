"""Operator tests with DuckDB and the connection fully mocked."""

from __future__ import annotations

from unittest import mock

from warehouse.hooks import DuckDBWarehouseHook
from warehouse.operators import CsvPartitionToDuckDBOperator


def test_execute_deletes_then_inserts_partition():
    fake_conn = mock.MagicMock(host="/tmp/wh.duckdb", schema="raw", extra_dejson={})
    with mock.patch.object(DuckDBWarehouseHook, "get_connection", return_value=fake_conn), \
            mock.patch("duckdb.connect") as connect:
        con = connect.return_value
        con.execute.return_value.fetchone.return_value = (2,)
        op = CsvPartitionToDuckDBOperator(
            task_id="load",
            csv_path="orders.csv",
            table="orders",
            partition_column="order_date",
            partition_date="2026-03-02",
            duckdb_conn_id="warehouse",
        )
        assert op.execute(context={}) == 2
    statements = " ".join(str(c.args[0]) for c in con.execute.call_args_list)
    assert "DELETE" in statements
    assert "INSERT" in statements
    con.close.assert_called_once()
