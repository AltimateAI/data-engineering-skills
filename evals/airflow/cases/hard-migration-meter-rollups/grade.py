"""Grader for hard-migration-meter-rollups.

The fixture is an Airflow 2.11 metering project: two generated hourly regional
loaders (custom plugin operator, dataset outlets), a rollup scheduled on
``east & west`` that works on its run's data interval and reads
``triggering_dataset_events``, a daily tariff sync and daily billing driven by
``.sh`` templates (removed context keys, ``conf`` and a plugin macro), and a
registry export.

The original project is replayed in the 2.11 env and the agent's project in the
3.3 env with the same sequence of scheduled runs, scheduler-style
dataset/asset-triggered runs (batched events), and CLI triggers without a
logical date (see ``hardsim``). Task code runs with the Airflow 3 worker's
metadata-DB block emulated. Every file under ``output/`` must match.

What only shows at runtime on 3.3: asset-triggered runs have no data interval
(2.x derived one from the triggering events' source runs), the triggering and
outlet event accessors no longer accept URI strings, ``conf`` is gone from
the template context, ``tomorrow_ds``/``execution_date`` are gone, CLI triggers
have no ``ds``/``data_interval_*``, and bare cron/preset schedules become
trigger timetables.
"""

from __future__ import annotations

import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR))
import hardsim as hs  # noqa: E402

DAG_SHAPES = {
    "readings_east_hourly": ({"land_readings"}, []),
    "readings_west_hourly": ({"land_readings"}, []),
    "usage_rollup": ({"rollup"}, []),
    "tariffs_daily": ({"sync_tariffs"}, []),
    "billing_daily": ({"bill", "publish_invoices"}, [["bill", "publish_invoices"]]),
    "meter_registry_daily": ({"export_registry"}, []),
}
D = "2026-03-05T{}:00:00+00:00"
STEPS = [
    ["tariffs_daily", "2026-03-05T01:00:00+00:00"],
    ["tariffs_daily", "2026-03-06T01:00:00+00:00"],
    ["meter_registry_daily", "2026-03-06T00:00:00+00:00"],
    ["readings_east_hourly", D.format("01")],
    ["readings_east_hourly", D.format("02")],
    ["readings_west_hourly", D.format("01")],
    ["usage_rollup", hs.asset_trigger("2026-03-05T02:10:00+00:00")],
    ["readings_west_hourly", D.format("02")],
    ["readings_west_hourly", D.format("03")],
    ["readings_east_hourly", D.format("03")],
    ["usage_rollup", hs.asset_trigger("2026-03-05T03:10:00+00:00")],
    ["billing_daily", "2026-03-06T02:30:00+00:00"],
    ["readings_east_hourly", D.format("04")],
    ["readings_west_hourly", D.format("04")],
    ["usage_rollup", hs.asset_trigger("2026-03-05T04:10:00+00:00")],
    ["tariffs_daily", hs.trigger("2026-03-06T09:20:00+00:00")],
    ["billing_daily", hs.trigger("2026-03-07T01:15:00+00:00")],
]
AREAS = [
    ("hourly regional loads land the same readings files", ("lake/readings/",)),
    ("tariff syncs (scheduled and the CLI-triggered correction) write the same files", ("lake/tariffs/",)),
    ("asset-triggered rollups cover the same hours with the same manifests", ("rollup/",)),
    ("billing and invoice publication (scheduled and the CLI-triggered re-bill) match", ("billing/", "dropbox/")),
    ("registry snapshot matches", ("registry/",)),
]


def env_extra(ws: Path) -> dict:
    return {"AIRFLOW__CORE__PLUGINS_FOLDER": str(ws / "plugins"),
            "AIRFLOW__METERING__INVOICE_DROPBOX": str(ws / "output" / "dropbox")}


if __name__ == "__main__":
    hs.grade_project(CASE_DIR, dag_shapes=DAG_SHAPES, steps=STEPS, areas=AREAS, env_extra=env_extra)
