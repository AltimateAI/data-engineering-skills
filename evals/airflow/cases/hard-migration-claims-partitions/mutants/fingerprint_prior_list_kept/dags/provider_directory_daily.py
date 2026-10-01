"""Daily provider-directory snapshot (effective for the previous day).

Writes output/lake/providers/<day>.csv plus <day>.status, which says whether the
directory changed since the previous snapshot (network managers only review
changed days). The snapshot fingerprint is kept in XCom between runs.
"""

from __future__ import annotations

import csv
import hashlib

import pendulum
from airflow.sdk import CronDataIntervalTimetable, dag, task

from claims_lib import LAKE
from claims_lib.assets import PROVIDERS
from claims_lib.hooks import ClaimsExportHook

COLUMNS = ("provider_id", "name", "network")


@dag(
    schedule=CronDataIntervalTimetable("0 3 * * *", timezone="UTC"),
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "claims-data", "retries": 1},
    tags=["claims", "reference-data"],
)
def provider_directory_daily():
    @task(outlets=[PROVIDERS])
    def sync_providers(ds=None, ti=None) -> str:
        rows = [r for r in ClaimsExportHook().read("providers_export.csv") if r["valid_from"] == ds]
        out = LAKE / "providers" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(COLUMNS))
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r[k] for k in COLUMNS})

        fingerprint = hashlib.sha256(
            "\n".join(",".join(r[k] for k in COLUMNS) for r in rows).encode()).hexdigest()
        previous = ti.xcom_pull(task_ids="sync_providers", key="fingerprint", include_prior_dates=True)
        status = "first snapshot" if previous is None else ("unchanged" if previous == fingerprint else "changed")
        (LAKE / "providers" / f"{ds}.status").write_text(status + "\n")
        ti.xcom_push(key="fingerprint", value=fingerprint)
        return ds  # directory version consumed by denials_digest_daily

    sync_providers()


provider_directory_daily()
