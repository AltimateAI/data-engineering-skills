"""Weekly campaign performance report.

Every Monday at 06:00 UTC it summarises the previous Monday-to-Sunday week
(UTC) per campaign and publishes a manifest for the growth dashboard.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, DeadlineAlert, DeadlineReference, SyncCallback
from airflow.timetables.interval import CronDataIntervalTimetable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENTS = PROJECT_ROOT / "data" / "campaign_events.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"
WEEK = timedelta(days=7)


def page_growth_oncall(context, **_):
    print("SLA missed: weekly_campaign_report still running at 09:00 UTC")


def summarize_week(data_interval_start, data_interval_end, **_):
    start, end = data_interval_start.date().isoformat(), data_interval_end.date().isoformat()
    spend: dict[str, float] = defaultdict(float)
    conversions: dict[str, int] = defaultdict(int)
    with EVENTS.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if start <= row["event_ts"][:10] < end:
                spend[row["campaign_id"]] += float(row["spend"])
                conversions[row["campaign_id"]] += int(row["conversions"])
    out = OUTPUT_DIR / "weekly" / f"{start}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["campaign_id", "spend", "conversions", "cost_per_conversion"])
        for cid in sorted(spend):
            conv = conversions[cid]
            cpc = f"{spend[cid] / conv:.2f}" if conv else ""
            writer.writerow([cid, f"{spend[cid]:.2f}", conv, cpc])
    return {"week_start": start, "week_end": end, "campaigns": len(spend)}


def publish_manifest(ti, **_):
    summary = ti.xcom_pull(task_ids="summarize_week")
    out = OUTPUT_DIR / "manifests" / f"{summary['week_start']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, sort_keys=True))


with DAG(
    dag_id="weekly_campaign_report",
    schedule=CronDataIntervalTimetable("0 6 * * 1", timezone="UTC"),
    start_date=pendulum.datetime(2026, 1, 5, tz="UTC"),
    catchup=True,
    default_args={"owner": "growth-analytics", "retries": 1},
    # The logical date is the start of the reported week, so the old 3h SLA
    # (measured from the Monday 06:00 run) is logical_date + 7 days + 3 hours.
    deadline=DeadlineAlert(
        reference=DeadlineReference.DAGRUN_LOGICAL_DATE,
        interval=WEEK + timedelta(hours=3),
        callback=SyncCallback(page_growth_oncall),
    ),
    max_active_runs=2,
    tags=["marketing", "weekly"],
) as dag:
    summarize = PythonOperator(task_id="summarize_week", python_callable=summarize_week)
    publish = PythonOperator(task_id="publish_manifest", python_callable=publish_manifest)
    summarize >> publish
