"""Daily count of events per event type (Airflow 2 idioms: fails to import on 3.3)."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dag(schedule_interval="@daily", start_date=days_ago(1), catchup=False, tags=["events"])
def event_counts():
    @task
    def count_events(ds=None):
        counts: Counter[str] = Counter()
        with (PROJECT_ROOT / "data" / "events.csv").open(newline="") as fh:
            for row in csv.DictReader(fh):
                if row["event_date"] == ds:
                    counts[row["event_type"]] += 1
        out = PROJECT_ROOT / "output" / "event_counts" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["event_type", "count"])
            for event_type in sorted(counts):
                writer.writerow([event_type, counts[event_type]])
        return str(out)

    count_events()


event_counts()
