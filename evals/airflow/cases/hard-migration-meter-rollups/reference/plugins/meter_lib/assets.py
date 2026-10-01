"""Datasets and paths shared by the metering DAGs."""

from __future__ import annotations

import json
from pathlib import Path

from airflow.sdk import Asset

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAKE = PROJECT_ROOT / "output" / "lake"
REGIONS: list[str] = json.loads((PROJECT_ROOT / "config" / "regions.json").read_text())["regions"]

READINGS = {region: Asset(f"lake://metering/readings/{region}") for region in REGIONS}
