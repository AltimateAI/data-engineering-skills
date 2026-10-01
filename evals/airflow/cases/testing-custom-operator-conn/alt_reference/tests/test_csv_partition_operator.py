import os
import sys
import tempfile
import unittest
from unittest import mock

import duckdb
from airflow.sdk import Connection

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

from warehouse.hooks import DuckDBWarehouseHook  # noqa: E402
from warehouse.operators import CsvPartitionToDuckDBOperator  # noqa: E402

CSV = """refund_id,refund_date,order_id,amount
R1,2026-04-01,O1,5.00
R2,2026-04-01,O2,6.00
R3,2026-04-02,O3,7.00
"""


class CsvPartitionToDuckDBOperatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "warehouse.duckdb")
        self.csv = os.path.join(self.tmp.name, "refunds.csv")
        with open(self.csv, "w") as fh:
            fh.write(CSV)
        conns = {
            "finance_wh": Connection(conn_id="finance_wh", conn_type="duckdb", host=self.db, schema="finance"),
        }
        patcher = mock.patch.object(DuckDBWarehouseHook, "get_connection", side_effect=lambda cid: conns[cid])
        self.get_connection = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def run_for(self, day):
        op = CsvPartitionToDuckDBOperator(
            task_id="load_refunds",
            csv_path=self.csv,
            table="refunds",
            partition_column="refund_date",
            partition_date=day,
            duckdb_conn_id="finance_wh",
        )
        return op.execute(context={})

    def table(self):
        with duckdb.connect(self.db, read_only=True) as con:
            return con.execute("SELECT refund_id, refund_date FROM finance.refunds ORDER BY refund_id").fetchall()

    def test_first_load(self):
        self.assertEqual(self.run_for("2026-04-01"), 2)
        self.assertEqual(self.table(), [("R1", "2026-04-01"), ("R2", "2026-04-01")])
        self.get_connection.assert_called_with("finance_wh")

    def test_idempotent_rerun(self):
        self.run_for("2026-04-01")
        self.run_for("2026-04-02")
        self.run_for("2026-04-01")
        self.assertEqual(
            self.table(), [("R1", "2026-04-01"), ("R2", "2026-04-01"), ("R3", "2026-04-02")]
        )


if __name__ == "__main__":
    unittest.main()
