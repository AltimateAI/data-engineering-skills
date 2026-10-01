"""Inventory snapshot DAG written with TaskFlow and pandas."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from airflow.decorators import dag, task
from airflow.operators.empty import EmptyOperator

ROOT = Path(__file__).resolve().parent.parent


@dag(
    schedule="30 2 * * *",
    start_date=datetime(2026, 8, 15, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["inventory"],
)
def inventory_snapshot():
    @task
    def snapshot(ds=None) -> str:
        import pandas as pd

        moves = pd.read_csv(ROOT / "data" / "inventory_movements.csv")
        moves = moves[moves["movement_date"] <= ds]
        stock = (
            moves.groupby(["warehouse_id", "sku"], as_index=False)["qty_change"].sum()
            .rename(columns={"qty_change": "on_hand"})
            .sort_values(["warehouse_id", "sku"])
        )
        out = ROOT / "output" / "inventory_snapshot" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        stock.to_csv(out, index=False)
        return str(out)

    @task
    def low_stock(snapshot_path: str, ds=None) -> str:
        import pandas as pd

        stock = pd.read_csv(snapshot_path)
        points = pd.read_csv(ROOT / "data" / "reorder_points.csv")
        low = stock.merge(points, on="sku")
        low = low[low["on_hand"] < low["reorder_point"]].sort_values(["warehouse_id", "sku"])
        out = ROOT / "output" / "low_stock" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        low[["warehouse_id", "sku", "on_hand", "reorder_point"]].to_csv(out, index=False)
        return str(out)

    done = EmptyOperator(task_id="done")
    low_stock(snapshot()) >> done


inventory_snapshot()
