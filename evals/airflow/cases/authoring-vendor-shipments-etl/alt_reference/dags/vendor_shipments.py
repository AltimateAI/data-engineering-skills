"""Vendor shipments DAG written with TaskFlow sensors and a TaskFlow bash task."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow.sdk import PokeReturnValue, Variable, dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = PROJECT_ROOT / "warehouse" / "analytics.duckdb"


def vendor_file(ds: str) -> Path:
    return Path(Variable.get("vendor_landing_dir")) / f"shipments_{ds}.csv"


@dag(
    dag_id="vendor_shipments",
    schedule="0 6 * * *",
    start_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["shipments"],
)
def build():
    @task.sensor(mode="reschedule", poke_interval=600, timeout=timedelta(hours=17))
    def vendor_file_arrived(ds=None) -> PokeReturnValue:
        path = vendor_file(ds)
        return PokeReturnValue(is_done=path.exists(), xcom_value=str(path))

    @task
    def load(path: str, ds=None) -> int:
        import duckdb
        import pandas as pd

        frame = pd.read_csv(path, dtype={"shipment_id": str})
        frame["ship_date"] = pd.to_datetime(ds).date()
        WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(WAREHOUSE))
        try:
            con.register("incoming", frame)
            con.execute("CREATE TABLE IF NOT EXISTS vendor_shipments AS SELECT * FROM incoming LIMIT 0")
            con.execute("DELETE FROM vendor_shipments WHERE ship_date = ?", [frame["ship_date"].iloc[0]])
            con.execute("INSERT INTO vendor_shipments SELECT * FROM incoming")
        finally:
            con.close()
        return len(frame)

    @task.bash
    def publish_report(rows: int, ds=None) -> str:
        return f"bash {PROJECT_ROOT / 'scripts' / 'publish_shipments_report.sh'} {ds}"

    publish_report(load(vendor_file_arrived()))


build()
