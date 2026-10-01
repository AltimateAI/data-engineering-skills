"""Partner feeds with a classic PythonOperator mapped via expand(op_kwargs=...)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, task

BASE = Path(__file__).resolve().parents[1]


def load_partner_file(path: str, ds: str) -> None:
    import pandas as pd

    frame = pd.read_csv(path)
    partner = Path(path).stem
    out_dir = BASE / "output" / "partner_feeds" / ds
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{partner}.json").write_text(json.dumps({
        "partner": partner,
        "rows": int(len(frame)),
        "total_amount": float(round(frame["amount"].sum(), 2)),
    }))


with DAG(
    dag_id="partner_feeds",
    schedule="@daily",
    start_date=datetime(2026, 8, 1),
    catchup=False,
    max_active_runs=1,
):

    @task
    def find_files(ds=None) -> list[dict]:
        folder = BASE / "data" / "partner_drop" / ds
        return [{"path": str(p), "ds": ds} for p in sorted(folder.glob("*.csv"))]

    per_file = PythonOperator.partial(task_id="load_partner_file", python_callable=load_partner_file).expand(
        op_kwargs=find_files()
    )

    @task(trigger_rule="none_failed")
    def summary(ds=None) -> None:
        out_dir = BASE / "output" / "partner_feeds" / ds
        out_dir.mkdir(parents=True, exist_ok=True)
        parts = [json.loads(p.read_text()) for p in sorted(out_dir.glob("*.json")) if p.name != "summary.json"]
        (out_dir / "summary.json").write_text(json.dumps({
            "files": len(parts),
            "rows": sum(p["rows"] for p in parts),
            "total_amount": round(sum(p["total_amount"] for p in parts), 2),
        }))

    per_file >> summary()
