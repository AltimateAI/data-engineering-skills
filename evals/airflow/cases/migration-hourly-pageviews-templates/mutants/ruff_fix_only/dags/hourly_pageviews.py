"""Hourly pageview rollup for the product analytics dashboard.

At the top of every hour it takes the previous clock hour of raw pageview
events, stages them, aggregates views and unique sessions per page (with the
change against the hour before) and drops a completion marker that the
dashboard loader waits for. Staged extracts are kept for a day: every run
deletes the staging files from the day before its hour.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENTS = PROJECT_ROOT / "data" / "pageviews.jsonl"
OUTPUT = PROJECT_ROOT / "output"
STAGING = OUTPUT / "staging"
HOURLY = OUTPUT / "hourly"


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def extract_hour(start: str, end: str, hour: str) -> int:
    """Stage the raw events with start <= ts < end."""
    lo, hi = _parse(start), _parse(end)
    STAGING.mkdir(parents=True, exist_ok=True)
    count = 0
    with EVENTS.open() as src, (STAGING / f"{hour}.csv").open("w", newline="") as dst:
        writer = csv.writer(dst)
        writer.writerow(["ts", "session_id", "page"])
        for line in src:
            event = json.loads(line)
            if lo <= _parse(event["ts"]) < hi:
                writer.writerow([event["ts"], event["session_id"], event["page"]])
                count += 1
    return count


def aggregate_hour(hour: str, prev_hour: str) -> None:
    views: dict[str, int] = defaultdict(int)
    sessions: dict[str, set[str]] = defaultdict(set)
    with (STAGING / f"{hour}.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            views[row["page"]] += 1
            sessions[row["page"]].add(row["session_id"])

    previous: dict[str, int] = {}
    prev_file = HOURLY / f"{prev_hour}.csv"
    if prev_file.exists():
        with prev_file.open(newline="") as fh:
            previous = {row["page"]: int(row["views"]) for row in csv.DictReader(fh)}

    HOURLY.mkdir(parents=True, exist_ok=True)
    with (HOURLY / f"{hour}.csv").open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["page", "views", "sessions", "views_change"])
        for page in sorted(views):
            change = views[page] - previous[page] if page in previous else ""
            writer.writerow([page, views[page], len(sessions[page]), change])


with DAG(
    dag_id="hourly_pageviews",
    schedule="0 * * * *",
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "product-analytics", "retries": 2, "retry_delay": timedelta(minutes=2)},
    params={"output": str(OUTPUT)},
    tags=["analytics", "hourly"],
) as dag:
    extract = PythonOperator(
        task_id="extract_hour",
        python_callable=extract_hour,
        op_kwargs={
            "start": "{{ execution_date }}",
            "end": "{{ next_execution_date }}",
            "hour": "{{ execution_date.strftime('%Y%m%dT%H') }}",
        },
    )
    aggregate = PythonOperator(
        task_id="aggregate_hour",
        python_callable=aggregate_hour,
        op_kwargs={
            "hour": "{{ execution_date.strftime('%Y%m%dT%H') }}",
            "prev_hour": "{{ prev_execution_date.strftime('%Y%m%dT%H') }}",
        },
    )
    publish = BashOperator(
        task_id="publish_hour",
        bash_command=(
            "mkdir -p {{ params.output }}/markers && "
            "echo \"hour={{ execution_date.strftime('%Y-%m-%dT%H:00') }} "
            "staged={{ ti.xcom_pull(task_ids='extract_hour') }}\" "
            "> {{ params.output }}/markers/{{ ts_nodash }}.done && "
            "find {{ params.output }}/staging -name '{{ yesterday_ds_nodash }}T*.csv' -delete"
        ),
    )
    extract >> aggregate >> publish
