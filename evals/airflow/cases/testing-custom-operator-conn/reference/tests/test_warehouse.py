"""Unit tests for the DuckDB warehouse hook and CSV partition loader.

Connections come from AIRFLOW_CONN_* env vars, so no metadata DB is needed.
"""

from __future__ import annotations

import json

import duckdb
import pytest
from warehouse.hooks import DuckDBWarehouseHook
from warehouse.operators import CsvPartitionToDuckDBOperator

CONN_ID = "test_wh"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "wh.duckdb"
    conn = {"conn_type": "duckdb", "host": str(path), "schema": "raw_test"}
    monkeypatch.setenv(f"AIRFLOW_CONN_{CONN_ID.upper()}", json.dumps(conn))
    return path


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "orders.csv"
    path.write_text(
        "order_id,order_date,amount\n"
        "A1,2026-03-01,10.00\n"
        "A2,2026-03-02,20.00\n"
        "A3,2026-03-02,30.00\n"
        "A4,2026-03-03,40.00\n"
    )
    return path


def make_op(csv_path, day, conn_id=CONN_ID):
    return CsvPartitionToDuckDBOperator(
        task_id="load",
        csv_path=str(csv_path),
        table="orders",
        partition_column="order_date",
        partition_date=day,
        duckdb_conn_id=conn_id,
    )


def rows(db_path, sql):
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_hook_reads_connection_fields(db_path):
    hook = DuckDBWarehouseHook(duckdb_conn_id=CONN_ID)
    assert hook.database_path == str(db_path)
    assert hook.target_schema == "raw_test"
    con = hook.get_conn()
    con.execute("create table t as select 1 as x")
    con.close()
    assert rows(db_path, "select x from t") == [(1,)]


def test_loads_only_the_partition_into_connection_schema(db_path, csv_path):
    loaded = make_op(csv_path, "2026-03-02").execute(context={})
    assert loaded == 2
    assert rows(db_path, "select order_id from raw_test.orders order by 1") == [("A2",), ("A3",)]


def test_rerun_replaces_partition_and_keeps_other_dates(db_path, csv_path):
    make_op(csv_path, "2026-03-01").execute(context={})
    make_op(csv_path, "2026-03-02").execute(context={})
    assert make_op(csv_path, "2026-03-02").execute(context={}) == 2
    assert rows(db_path, "select order_id from raw_test.orders order by 1") == [("A1",), ("A2",), ("A3",)]


def test_unknown_connection_fails(db_path, csv_path):
    with pytest.raises(Exception, match="missing_conn"):
        make_op(csv_path, "2026-03-02", conn_id="missing_conn").execute(context={})
