"""Daily ingest of partner manifests."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import dag, task

from partners.sensors import PartnerManifestSensor


@dag(
    schedule="0 4 * * *",
    start_date=datetime(2026, 9, 1),
    catchup=False,
    default_args={"retries": 3, "retry_delay": timedelta(minutes=2)},
    tags=["partners"],
)
def partner_ingest():
    @task
    def prepare_staging(ds=None):
        print(f"staging prepared for {ds}")

    @task
    def load(partner: str, files: list[str]):
        print(f"loading {len(files)} {partner} files")
        return len(files)

    staging = prepare_staging()
    # acme feeds finance reporting: wait up to 6 hours, then page.
    acme = PartnerManifestSensor(task_id="wait_acme", partner="acme", poke_interval=300, timeout=6 * 3600)
    # globex is nice to have: give up quietly after 3 hours.
    globex = PartnerManifestSensor(
        task_id="wait_globex", partner="globex", poke_interval=300, timeout=3 * 3600, soft_fail=True
    )
    staging >> [acme, globex]
    load.override(task_id="load_acme")("acme", acme.output)
    load.override(task_id="load_globex")("globex", globex.output)


partner_ingest()
