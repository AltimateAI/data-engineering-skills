"""Clickstream page stats with pandas; intermediate data goes to run-scoped CSV files."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = Path(os.environ.get("CLICKSTREAM_SCRATCH", tempfile.gettempdir())) / "clickstream_page_stats"


def _scratch(run_id: str) -> Path:
    path = SCRATCH / run_id.replace(":", "_").replace("+", "_")
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_day(ds: str, run_id: str) -> str:
    import pandas as pd

    events = pd.read_csv(ROOT / "data" / "clickstream" / f"{ds}.csv.gz", dtype={"user_id": "string"})
    events = events[(events["is_bot"] == 0) & events["user_id"].notna()]
    path = _scratch(run_id) / "events.csv"
    events[["user_id", "page", "load_ms"]].to_csv(path, index=False)
    return str(path)


def transform_day(ds: str, run_id: str, ti) -> str:
    import pandas as pd

    events = pd.read_csv(ti.xcom_pull(task_ids="extract"))
    stats = (
        events.groupby("page")
        .agg(views=("page", "size"), unique_users=("user_id", "nunique"), avg_load_ms=("load_ms", "mean"))
        .reset_index()
        .sort_values("page")
    )
    stats["avg_load_ms"] = stats["avg_load_ms"].round(1)
    path = _scratch(run_id) / "stats.csv"
    stats.to_csv(path, index=False)
    return str(path)


def load_day(ds: str, ti) -> None:
    import shutil

    out = ROOT / "output" / "page_stats" / f"{ds}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ti.xcom_pull(task_ids="transform"), out)


with DAG(
    dag_id="clickstream_page_stats",
    schedule="0 5 * * *",
    start_date=datetime(2026, 9, 1),
    catchup=False,
) as dag:
    extract = PythonOperator(task_id="extract", python_callable=extract_day)
    transform = PythonOperator(task_id="transform", python_callable=transform_day)
    load = PythonOperator(task_id="load", python_callable=load_day)
    extract >> transform >> load
