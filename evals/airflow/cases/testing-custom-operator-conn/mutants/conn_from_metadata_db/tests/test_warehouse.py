"""Tests that rely on the `warehouse` connection created locally with
`airflow connections add warehouse --conn-json ...` (not present in CI)."""

from __future__ import annotations

import duckdb
from warehouse.hooks import DuckDBWarehouseHook
from warehouse.operators import CsvPartitionToDuckDBOperator


def make_op(csv_path, day):
    return CsvPartitionToDuckDBOperator(
        task_id="load",
        csv_path=str(csv_path),
        table="orders_test",
        partition_column="order_date",
        partition_date=day,
        duckdb_conn_id="warehouse",
    )


def test_loads_partition_and_is_idempotent(tmp_path):
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text("order_id,order_date\nA1,2026-03-01\nA2,2026-03-02\nA3,2026-03-02\n")
    hook = DuckDBWarehouseHook(duckdb_conn_id="warehouse")
    make_op(csv_path, "2026-03-01").execute(context={})
    make_op(csv_path, "2026-03-02").execute(context={})
    assert make_op(csv_path, "2026-03-02").execute(context={}) == 2
    con = duckdb.connect(hook.database_path, read_only=True)
    got = con.execute(f"select order_id from {hook.target_schema}.orders_test order by 1").fetchall()
    con.close()
    assert got == [("A1",), ("A2",), ("A3",)]
