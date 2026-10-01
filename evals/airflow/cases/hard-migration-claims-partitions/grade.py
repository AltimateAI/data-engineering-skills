"""Grader for hard-migration-claims-partitions.

The fixture is an Airflow 2.11 claims project: an hourly intake that attaches
the service-date partitions it touched to a DatasetAlias (custom hook on an
``fs`` connection), a consumer scheduled on the alias that rebuilds exactly the
partitions named by ``triggering_dataset_events`` (keyed by dataset URI), a
directory snapshot whose version a digest reads with a cross-DAG
``xcom_pull(include_prior_dates=True)``, and a manual-only reprocess DAG
triggered with config that uses the run's ``logical_date`` as its cutoff.

The original is replayed in the 2.11 env and the agent's project in the 3.3 env
(task code under the Airflow 3 worker's metadata-DB block): scheduled runs,
scheduler-style alias-triggered runs and a CLI trigger with config. Every file
under ``output/`` must match. See ``hardsim``.
"""

from __future__ import annotations

import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR))
import hardsim as hs  # noqa: E402

DAG_SHAPES = {
    "claims_intake_hourly": ({"land_claims"}, []),
    "claims_service_date_marts": ({"rebuild_partitions", "publish_ready"}, [["rebuild_partitions", "publish_ready"]]),
    "provider_directory_daily": ({"sync_providers"}, []),
    "denials_digest_daily": ({"build_digest"}, []),
    "claims_reprocess": ({"recheck_partition", "log_recheck"}, [["recheck_partition", "log_recheck"]]),
}
STEPS = [
    ["provider_directory_daily", "2026-03-04T03:00:00+00:00"],
    ["provider_directory_daily", "2026-03-05T03:00:00+00:00"],
    ["claims_intake_hourly", "2026-03-04T21:00:00+00:00"],
    ["claims_intake_hourly", "2026-03-04T22:00:00+00:00"],
    ["claims_intake_hourly", "2026-03-04T23:00:00+00:00"],
    ["claims_service_date_marts", hs.asset_trigger("2026-03-04T23:05:00+00:00")],
    ["claims_intake_hourly", "2026-03-05T00:00:00+00:00"],
    ["claims_intake_hourly", "2026-03-05T01:00:00+00:00"],
    ["claims_service_date_marts", hs.asset_trigger("2026-03-05T01:05:00+00:00")],
    ["denials_digest_daily", "2026-03-05T07:00:00+00:00"],
    ["provider_directory_daily", "2026-03-06T03:00:00+00:00"],
    ["denials_digest_daily", "2026-03-06T07:00:00+00:00"],
    ["claims_reprocess", hs.trigger("2026-03-06T09:00:00+00:00", {"service_date": "2026-03-04"})],
    ["claims_service_date_marts", hs.asset_trigger("2026-03-06T09:05:00+00:00")],
    # the 03-07 directory sync has not run (late export): the digest falls back to the latest snapshot
    ["denials_digest_daily", "2026-03-07T07:00:00+00:00"],
]
AREAS = [
    ("hourly intake lands the same partition files", ("lake/claims/",)),
    ("partition marts, rebuild records and the READY list match", ("marts/",)),
    ("provider directory snapshots match", ("lake/providers/",)),
    ("denials digests use the same directory versions and rows", ("digests/",)),
]


def env_extra(ws: Path) -> dict:
    conn = '{"conn_type": "fs", "extra": {"export_dir": "%s"}}' % (ws / "data")
    return {"AIRFLOW__CORE__PLUGINS_FOLDER": str(ws / "plugins"), "AIRFLOW_CONN_CLAIMS_EXPORT": conn}


if __name__ == "__main__":
    hs.grade_project(CASE_DIR, dag_shapes=DAG_SHAPES, steps=STEPS, areas=AREAS, env_extra=env_extra)
