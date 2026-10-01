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
from airflow.sdk import CronTriggerTimetable, dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENTS = PROJECT_ROOT / "data" / "pageviews.jsonl"
OUTPUT = PROJECT_ROOT / "output"
STAGING = OUTPUT / "staging"
HOURLY = OUTPUT / "hourly"
MARKERS = OUTPUT / "markers"


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _hour_key(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H")


@dag(
    # Runs at the top of the hour; the data interval is the hour that just ended.
    schedule=CronTriggerTimetable("0 * * * *", timezone="UTC", interval=timedelta(hours=1)),
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "product-analytics", "retries": 2, "retry_delay": timedelta(minutes=2)},
    tags=["analytics", "hourly"],
)
def hourly_pageviews():
    @task
    def extract_hour(data_interval_start=None, data_interval_end=None) -> int:
        STAGING.mkdir(parents=True, exist_ok=True)
        count = 0
        with EVENTS.open() as src, (STAGING / f"{_hour_key(data_interval_start)}.csv").open("w", newline="") as dst:
            writer = csv.writer(dst)
            writer.writerow(["ts", "session_id", "page"])
            for line in src:
                event = json.loads(line)
                if data_interval_start <= _parse(event["ts"]) < data_interval_end:
                    writer.writerow([event["ts"], event["session_id"], event["page"]])
                    count += 1
        return count

    @task
    def aggregate_hour(data_interval_start=None) -> None:
        views: dict[str, int] = defaultdict(int)
        sessions: dict[str, set[str]] = defaultdict(set)
        with (STAGING / f"{_hour_key(data_interval_start)}.csv").open(newline="") as fh:
            for row in csv.DictReader(fh):
                views[row["page"]] += 1
                sessions[row["page"]].add(row["session_id"])

        prev_file = HOURLY / f"{_hour_key(data_interval_start - timedelta(hours=1))}.csv"
        previous: dict[str, int] = {}
        if prev_file.exists():
            with prev_file.open(newline="") as fh:
                previous = {row["page"]: int(row["views"]) for row in csv.DictReader(fh)}

        HOURLY.mkdir(parents=True, exist_ok=True)
        with (HOURLY / f"{_hour_key(data_interval_start)}.csv").open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["page", "views", "sessions", "views_change"])
            for page in sorted(views):
                change = views[page] - previous[page] if page in previous else ""
                writer.writerow([page, views[page], len(sessions[page]), change])

    @task
    def publish_hour(staged: int, data_interval_start=None) -> None:
        MARKERS.mkdir(parents=True, exist_ok=True)
        marker = MARKERS / f"{data_interval_start.strftime('%Y%m%dT%H%M%S')}.done"
        marker.write_text(f"hour={data_interval_start.strftime('%Y-%m-%dT%H:00')} staged={staged}\n")
        day_before = (data_interval_start - timedelta(days=1)).strftime("%Y%m%d")
        for stale in STAGING.glob(f"{day_before}T*.csv"):
            stale.unlink()

    staged = extract_hour()
    aggregated = aggregate_hour()
    staged >> aggregated >> publish_hour(staged)


hourly_pageviews()
