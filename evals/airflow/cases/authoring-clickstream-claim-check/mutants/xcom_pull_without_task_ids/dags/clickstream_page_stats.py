"""Clickstream page stats; claim-check paths pulled Airflow-2 style (no task_ids)."""

from __future__ import annotations

from pathlib import Path

import pendulum
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGING = PROJECT_ROOT / "staging" / "clickstream_page_stats"


def extract(ds, ti):
    import pandas as pd

    events = pd.read_csv(PROJECT_ROOT / "data" / "clickstream" / f"{ds}.csv.gz", dtype={"user_id": "string"})
    events = events[(events["is_bot"] == 0) & events["user_id"].notna()]
    path = STAGING / ds / "events.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(path, index=False)
    ti.xcom_push(key="events_path", value=str(path))


def transform(ds, ti):
    import pandas as pd

    events = pd.read_csv(ti.xcom_pull(key="events_path"))
    stats = (
        events.groupby("page")
        .agg(views=("page", "size"), unique_users=("user_id", "nunique"), avg_load_ms=("load_ms", "mean"))
        .reset_index()
        .sort_values("page")
    )
    stats["avg_load_ms"] = stats["avg_load_ms"].round(1)
    path = STAGING / ds / "stats.csv"
    stats.to_csv(path, index=False)
    ti.xcom_push(key="stats_path", value=str(path))


def load(ds, ti):
    import shutil

    out = PROJECT_ROOT / "output" / "page_stats" / f"{ds}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ti.xcom_pull(key="stats_path"), out)


with DAG(
    dag_id="clickstream_page_stats",
    schedule="0 5 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
):
    (
        PythonOperator(task_id="extract", python_callable=extract)
        >> PythonOperator(task_id="transform", python_callable=transform)
        >> PythonOperator(task_id="load", python_callable=load)
    )
