"""Nightly export of the partner registry for the finance team."""

from __future__ import annotations

import json
from pathlib import Path

import pendulum
from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dag(
    schedule="0 1 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    tags=["partners"],
)
def partner_registry_export():
    @task
    def export(ds=None) -> str:
        registry = json.loads((PROJECT_ROOT / "data" / "partners.json").read_text())
        out = PROJECT_ROOT / "output" / "partner_registry" / f"{ds}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(sorted(registry), indent=2))
        return str(out)

    export()


partner_registry_export()
