"""Daily vendor shipments: wait for the vendor file, load it, publish the carrier report."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.sensors.filesystem import FileSensor
from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = PROJECT_ROOT / "warehouse" / "analytics.duckdb"
# Rendered at run time, so parsing the file never reads the Variable.
VENDOR_FILE = "{{ var.value.vendor_landing_dir }}/shipments_{{ ds }}.csv"


@dag(
    schedule_interval="0 6 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "logistics-analytics", "retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["shipments", "warehouse"],
)
def vendor_shipments():
    wait_for_vendor_file = FileSensor(
        task_id="wait_for_vendor_file",
        filepath=VENDOR_FILE,
        deferrable=True,
        poke_interval=300,
        timeout=int(timedelta(hours=18).total_seconds()),
        retries=0,
    )

    @task(templates_dict={"path": VENDOR_FILE})
    def load_shipments(ds=None, templates_dict=None):
        import duckdb

        path = templates_dict["path"]
        WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(WAREHOUSE)) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS vendor_shipments (shipment_id VARCHAR, carrier VARCHAR, "
                "destination VARCHAR, weight_kg DOUBLE, shipped_at TIMESTAMP, ship_date DATE)"
            )
            con.execute("BEGIN TRANSACTION")
            con.execute("DELETE FROM vendor_shipments WHERE ship_date = CAST(? AS DATE)", [ds])
            con.execute(
                "INSERT INTO vendor_shipments SELECT shipment_id, carrier, destination, weight_kg, "
                "shipped_at, CAST(? AS DATE) FROM read_csv(?, header = true, "
                "columns = {'shipment_id': 'VARCHAR', 'carrier': 'VARCHAR', 'destination': 'VARCHAR', "
                "'weight_kg': 'DOUBLE', 'shipped_at': 'TIMESTAMP'})",
                [ds, path],
            )
            con.execute("COMMIT")
            return con.execute(
                "SELECT count(*) FROM vendor_shipments WHERE ship_date = CAST(? AS DATE)", [ds]
            ).fetchone()[0]

    publish_shipments_report = BashOperator(
        task_id="publish_shipments_report",
        bash_command=f"{PROJECT_ROOT}/scripts/publish_shipments_report.sh {{{{ ds }}}}",
    )

    wait_for_vendor_file >> load_shipments() >> publish_shipments_report


vendor_shipments()
