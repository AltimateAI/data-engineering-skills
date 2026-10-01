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
from airflow.sdk import (
    DeadlineAlert,
    DeadlineReference,
    SyncCallback,
    dag,
    task,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENTS = PROJECT_ROOT / "data" / "campaign_events.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"


def notify_growth_oncall(context=None, **kwargs):
    print("weekly_campaign_report missed its deadline (not finished 3h after the 06:00 UTC start)")


@dag(
    schedule="0 6 * * 1",
    start_date=pendulum.datetime(2026, 1, 5, tz="UTC"),
    # Airflow 2 defaulted to catchup=True and season re-runs rely on it.
    catchup=True,
    default_args={"owner": "growth-analytics", "retries": 1},
    # SLAs were removed in Airflow 3: page on-call when the run is not done
    # 3 hours after it was queued (06:00 -> 09:00 UTC).
    deadline=DeadlineAlert(
        reference=DeadlineReference.DAGRUN_QUEUED_AT,
        interval=timedelta(hours=3),
        callback=SyncCallback(notify_growth_oncall),
    ),
    max_active_runs=2,
    tags=["marketing", "weekly"],
)
def weekly_campaign_report():
    @task
    def summarize_week(ds=None, logical_date=None) -> dict:
        week_start = ds
        week_end = (logical_date + timedelta(days=7)).strftime("%Y-%m-%d")
        totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
        with EVENTS.open(newline="") as fh:
            for row in csv.DictReader(fh):
                if week_start <= row["event_ts"][:10] < week_end:
                    totals[row["campaign_id"]][0] += float(row["spend"])
                    totals[row["campaign_id"]][1] += int(row["conversions"])
        out = OUTPUT_DIR / "weekly" / f"{week_start}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["campaign_id", "spend", "conversions", "cost_per_conversion"])
            for cid in sorted(totals):
                spend, conv = totals[cid]
                writer.writerow([cid, f"{spend:.2f}", conv, f"{spend / conv:.2f}" if conv else ""])
        return {"week_start": week_start, "week_end": week_end, "campaigns": len(totals)}

    @task
    def publish_manifest(summary: dict) -> None:
        out = OUTPUT_DIR / "manifests" / f"{summary['week_start']}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, sort_keys=True))

    publish_manifest(summarize_week())


weekly_campaign_report()
