"""Smoke test: the operator runs against a temp DuckDB file and reports the row count."""

from __future__ import annotations

import json

from warehouse.operators import CsvPartitionToDuckDBOperator


def test_execute_returns_loaded_rows(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "AIRFLOW_CONN_TEST_WH",
        json.dumps({"conn_type": "duckdb", "host": str(tmp_path / "wh.duckdb"), "schema": "raw"}),
    )
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text("order_id,order_date\nA1,2026-03-01\nA2,2026-03-02\nA3,2026-03-02\n")
    op = CsvPartitionToDuckDBOperator(
        task_id="load",
        csv_path=str(csv_path),
        table="orders",
        partition_column="order_date",
        partition_date="2026-03-02",
        duckdb_conn_id="test_wh",
    )
    assert op.execute(context={}) == 2
