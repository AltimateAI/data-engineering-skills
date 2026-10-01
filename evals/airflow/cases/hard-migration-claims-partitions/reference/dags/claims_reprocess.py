"""On-demand re-check of one service-date partition (triggered by claims ops).

Trigger with config ``{"service_date": "YYYY-MM-DD"}``. Re-reads the export
for every claim of that service date received before the trigger time, writes
any claim missing from the partition to received_reprocess_<trigger time>.csv,
attaches the partition to the alias so the marts are rebuilt, and logs the
recheck (with the trigger time) to output/marts/_RECHECK_LOG.
"""

from __future__ import annotations

import csv

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import Param, dag, task

from claims_lib import LAKE, MARTS
from claims_lib.assets import CLAIMS_BY_SERVICE_DATE, partition_dataset
from claims_lib.hooks import ClaimsExportHook

FIELDS = ["claim_id", "provider_id", "service_date", "billed_cents", "status", "received_at"]


@dag(
    schedule=None,
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    params={"service_date": Param("2026-03-01", type="string", format="date")},
    default_args={"owner": "claims-ops"},
    tags=["claims", "ops"],
)
def claims_reprocess():
    @task(outlets=[CLAIMS_BY_SERVICE_DATE])
    def recheck_partition(params=None, dag_run=None, outlet_events=None) -> int:
        # A CLI/API trigger has no logical date on Airflow 3; the trigger time is run_after.
        logical_date = pendulum.instance(dag_run.logical_date or dag_run.run_after)
        day = params["service_date"]
        cutoff = logical_date.strftime("%Y-%m-%d %H:%M:%S")
        part = LAKE / "claims" / f"service_date={day}"
        landed = set()
        for path in part.glob("*.csv"):
            with path.open(newline="") as fh:
                landed |= {r["claim_id"] for r in csv.DictReader(fh)}
        missing = [r for r in ClaimsExportHook().read("claims_export.csv")
                   if r["service_date"] == day and r["received_at"] < cutoff and r["claim_id"] not in landed]
        if missing:
            part.mkdir(parents=True, exist_ok=True)
            with (part / f"received_reprocess_{logical_date.strftime('%Y%m%dT%H%M')}.csv").open("w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(missing)
        outlet_events[CLAIMS_BY_SERVICE_DATE].add(partition_dataset(day), extra={"claims": len(missing)})
        return len(missing)

    log_recheck = BashOperator(
        task_id="log_recheck",
        bash_command=(
            "echo \"{{ params.service_date }} rechecked at {{ (dag_run.logical_date or dag_run.run_after) | ts }}: "
            "{{ ti.xcom_pull(task_ids='recheck_partition') }} claim(s) recovered\" "
            f">> {MARTS}/_RECHECK_LOG"
        ),
    )
    recheck_partition() >> log_recheck


claims_reprocess()
