"""Golden-file regression guard: fail CI when any DAG source drifts from the reviewed version."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"
REVIEWED = {
    "carrier_rates_weekly.py": "e300d508e56e89e855bd4076d7a279cfbed32524a91ca9bfcd00505acf8575e7",
    "shipments_daily.py": "644e0ac4f3abd10f34cec1668d1842c80e39ef433ac481444b6babeceacde1fe",
}


@pytest.mark.parametrize("rel", sorted(REVIEWED))
def test_dag_source_matches_reviewed_version(rel):
    digest = hashlib.sha256((DAGS_DIR / rel).read_bytes()).hexdigest()
    assert digest == REVIEWED[rel], f"{rel} changed since review"
