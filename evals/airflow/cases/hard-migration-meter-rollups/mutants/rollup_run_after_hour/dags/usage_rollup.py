"""Hourly usage rollup, rebuilt once every region has landed new readings.

A run re-aggregates, for all regions, every hour from the start of the
earliest regional load that triggered it to the end of the latest one. When
several loads land close together the scheduler batches them into one run.
Output: output/rollup/usage_<first hour>_<end hour>.csv plus a .json manifest
with the raw row counts each region delivered to this run.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict

import pendulum
from airflow.sdk import dag, task

from meter_lib.assets import LAKE, PROJECT_ROOT, READINGS, REGIONS

ROLLUP_DIR = PROJECT_ROOT / "output" / "rollup"


def triggered_span(triggering_asset_events):
    """[start, end) from the earliest source-run interval start to the latest source-run
    interval end of the triggering events (what Airflow 2 gave asset-triggered runs as
    their data interval; Airflow 3 gives them none)."""
    starts, ends = [], []
    for events in triggering_asset_events.values():
        for event in events:
            run = event.source_dag_run
            if run is not None and run.data_interval_start is not None:
                starts.append(pendulum.instance(run.data_interval_start))
                ends.append(pendulum.instance(run.data_interval_end))
            else:
                starts.append(pendulum.instance(event.timestamp))
                ends.append(pendulum.instance(event.timestamp))
    return min(starts), max(ends)


@dag(
    schedule=(READINGS["east"] & READINGS["west"]),
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "metering"},
    tags=["metering", "rollup"],
)
def usage_rollup():
    @task
    def rollup(triggering_asset_events=None, dag_run=None) -> str:
        # asset-triggered runs have no interval on 3.x: roll up the hour before the run
        end = pendulum.instance(dag_run.run_after).start_of("hour")
        start = end.subtract(hours=1)
        usage: dict[tuple[str, str], float] = defaultdict(float)
        hours = set()
        for region in REGIONS:
            for path in sorted((LAKE / "readings" / region).glob("*.csv")):
                hour = pendulum.from_format(path.stem, "YYYYMMDDTHH", tz="UTC")
                if not start <= hour < end:
                    continue
                hours.add(hour.strftime("%Y-%m-%dT%H:00"))
                with path.open(newline="") as fh:
                    for row in csv.DictReader(fh):
                        usage[(row["meter_id"], hour.strftime("%Y-%m-%dT%H:00"))] += float(row["kwh"])

        name = f"usage_{start.strftime('%Y%m%dT%H')}_{end.strftime('%Y%m%dT%H')}"
        ROLLUP_DIR.mkdir(parents=True, exist_ok=True)
        with (ROLLUP_DIR / f"{name}.csv").open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["meter_id", "hour", "kwh"])
            for (meter, hour), kwh in sorted(usage.items()):
                writer.writerow([meter, hour, f"{kwh:.1f}"])

        delivered = {
            region: sum(event.extra.get("rows", 0) for event in triggering_asset_events.get(READINGS[region], []))
            for region in REGIONS
        }
        manifest = {"hours": sorted(hours), "rows_delivered": delivered}
        (ROLLUP_DIR / f"{name}.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return name

    rollup()


usage_rollup()
