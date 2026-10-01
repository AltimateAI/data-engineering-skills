"""Rebuilds the service-date marts for exactly the partitions that changed.

Triggered by the ``claims-by-service-date`` alias. For each partition named by
the triggering events it rebuilds output/marts/claims_by_service_date/<day>.csv
from all files of the partition, then records what it rebuilt (with the number
of new claims each partition received) in output/marts/rebuilds/, and appends
the partition list to output/marts/_READY_PARTITIONS for the BI refresh.
Rebuild records are numbered in run order.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict

import pendulum
from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator

from claims_lib import LAKE, MARTS
from claims_lib.assets import CLAIMS_BY_SERVICE_DATE, partition_of


def rebuild_mart(day: str) -> None:
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # claims, billed, denied
    for path in sorted((LAKE / "claims" / f"service_date={day}").glob("*.csv")):
        with path.open(newline="") as fh:
            for row in csv.DictReader(fh):
                s = stats[row["provider_id"]]
                s[0] += 1
                s[1] += int(row["billed_cents"])
                s[2] += row["status"] == "denied"
    out = MARTS / "claims_by_service_date" / f"{day}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["provider_id", "claims", "billed_cents", "denied"])
        for provider in sorted(stats):
            writer.writerow([provider, *stats[provider]])


@dag(
    schedule=[CLAIMS_BY_SERVICE_DATE],
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "claims-data"},
    tags=["claims", "marts"],
)
def claims_service_date_marts():
    @task
    def rebuild_partitions(triggering_dataset_events=None) -> list[str]:
        new_claims: dict[str, int] = defaultdict(int)
        for uri, events in triggering_dataset_events.items():
            new_claims[partition_of(uri)] += sum(event.extra.get("claims", 0) for event in events)
        days = sorted(new_claims)
        for day in days:
            rebuild_mart(day)
        records = MARTS / "rebuilds"
        records.mkdir(parents=True, exist_ok=True)
        record = records / f"{len(list(records.glob('*.json'))) + 1:04d}_{days[0]}_{days[-1]}.json"
        record.write_text(json.dumps({"new_claims": new_claims}, indent=2, sort_keys=True) + "\n")
        return days

    publish = BashOperator(
        task_id="publish_ready",
        bash_command=(
            "echo \"{{ ti.xcom_pull(task_ids='rebuild_partitions') | join(',') }}\" "
            f">> {MARTS}/_READY_PARTITIONS"
        ),
    )
    rebuild_partitions() >> publish


claims_service_date_marts()
