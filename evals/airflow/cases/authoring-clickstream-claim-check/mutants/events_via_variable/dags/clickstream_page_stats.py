"""Clickstream page stats; extract stashes the day's events in an Airflow Variable (metadata DB)."""

from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

import pendulum
from airflow.sdk import Variable, dag, task

ROOT = Path(__file__).resolve().parents[1]


@dag(schedule="@daily", start_date=pendulum.datetime(2026, 9, 1, tz="UTC"), catchup=False)
def clickstream_page_stats():
    @task
    def extract(ds=None) -> str:
        key = f"clickstream_events_{ds}"
        with gzip.open(ROOT / "data" / "clickstream" / f"{ds}.csv.gz", "rt", newline="") as src:
            events = [[r["user_id"], r["page"], int(r["load_ms"])] for r in csv.DictReader(src)
                      if r["is_bot"] != "1" and r["user_id"].strip()]
        Variable.set(key, json.dumps(events))
        return key

    @task
    def transform(key: str) -> list[dict]:
        views: dict[str, int] = defaultdict(int)
        users: dict[str, set] = defaultdict(set)
        total: dict[str, int] = defaultdict(int)
        for user, page, load_ms in json.loads(Variable.get(key)):
            views[page] += 1
            users[page].add(user)
            total[page] += load_ms
        return [{"page": p, "views": views[p], "unique_users": len(users[p]),
                 "avg_load_ms": round(total[p] / views[p], 1)} for p in sorted(views)]

    @task
    def load(stats: list[dict], ds=None) -> None:
        out = ROOT / "output" / "page_stats" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["page", "views", "unique_users", "avg_load_ms"])
            writer.writeheader()
            writer.writerows(stats)

    load(transform(extract()))


clickstream_page_stats()
