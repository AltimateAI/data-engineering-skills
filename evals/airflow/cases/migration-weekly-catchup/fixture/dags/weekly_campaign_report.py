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
from airflow.decorators import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENTS = PROJECT_ROOT / "data" / "campaign_events.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"


def notify_growth_oncall(dag, task_list, blocking_task_list, slas, blocking_tis):
    print(f"SLA missed for {task_list} in {dag.dag_id}")


@dag(
    schedule_interval="0 6 * * 1",
    start_date=pendulum.datetime(2026, 1, 5, tz="UTC"),
    default_args={"owner": "growth-analytics", "retries": 1, "sla": timedelta(hours=3)},
    sla_miss_callback=notify_growth_oncall,
    max_active_runs=2,
    tags=["marketing", "weekly"],
)
def weekly_campaign_report():
    @task
    def summarize_week(ds=None, next_ds=None) -> dict:
        totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
        with EVENTS.open(newline="") as fh:
            for row in csv.DictReader(fh):
                if ds <= row["event_ts"][:10] < next_ds:
                    totals[row["campaign_id"]][0] += float(row["spend"])
                    totals[row["campaign_id"]][1] += int(row["conversions"])
        out = OUTPUT_DIR / "weekly" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["campaign_id", "spend", "conversions", "cost_per_conversion"])
            for cid in sorted(totals):
                spend, conv = totals[cid]
                writer.writerow([cid, f"{spend:.2f}", conv, f"{spend / conv:.2f}" if conv else ""])
        return {"week_start": ds, "week_end": next_ds, "campaigns": len(totals)}

    @task
    def publish_manifest(summary: dict) -> None:
        out = OUTPUT_DIR / "manifests" / f"{summary['week_start']}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, sort_keys=True))

    publish_manifest(summarize_week())


weekly_campaign_report()
