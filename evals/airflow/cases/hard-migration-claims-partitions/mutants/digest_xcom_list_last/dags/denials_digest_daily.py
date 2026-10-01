"""Daily digest of denied claims for the previous service date, by provider.

Provider names and networks come from the latest provider-directory snapshot
taken at or before this run's date (its version is published in XCom by
provider_directory_daily). Output: output/digests/<service date>.csv
"""

from __future__ import annotations

import csv

import pendulum
from airflow.sdk import CronDataIntervalTimetable, dag, task

from claims_lib import LAKE, MARTS, PROJECT_ROOT


@dag(
    schedule=CronDataIntervalTimetable("0 7 * * *", timezone="UTC"),
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "claims-ops"},
    tags=["claims", "reporting"],
)
def denials_digest_daily():
    @task
    def build_digest(ds=None, ti=None) -> str:
        # Airflow 3 matches cross-DAG XCom pulls on this run's run_id, so the directory
        # DAG's values are not visible here; use the latest snapshot at or before ds.
        versions = ti.xcom_pull(dag_id="provider_directory_daily", task_ids="sync_providers", include_prior_dates=True)
        version = versions[-1] if isinstance(versions, list) else versions
        with (LAKE / "providers" / f"{version}.csv").open(newline="") as fh:
            directory = {r["provider_id"]: r for r in csv.DictReader(fh)}
        mart = MARTS / "claims_by_service_date" / f"{ds}.csv"
        rows = []
        if mart.exists():
            with mart.open(newline="") as fh:
                rows = [r for r in csv.DictReader(fh) if int(r["denied"]) > 0]
        out = PROJECT_ROOT / "output" / "digests" / f"{ds}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            fh.write(f"# directory version {version}\n")
            writer = csv.writer(fh)
            writer.writerow(["provider_id", "name", "network", "denied", "claims"])
            for r in rows:
                p = directory.get(r["provider_id"], {})
                writer.writerow([r["provider_id"], p.get("name", "?"), p.get("network", "?"), r["denied"], r["claims"]])
        return ds

    build_digest()


denials_digest_daily()
