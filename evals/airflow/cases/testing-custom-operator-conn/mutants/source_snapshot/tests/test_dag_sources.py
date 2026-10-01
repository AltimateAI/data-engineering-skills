"""Golden-file regression guard: fail CI when any DAG source drifts from the reviewed version."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"
REVIEWED = {
    "load_raw_sales.py": "38a00af47f57d1e3058650b55f01702a250019a863174ea3c7f7067938acffaf",
    "warehouse/__init__.py": "c45b2f9de5a495e409c73b74f4717935d091c74c936c14aded16f35c4ec23abd",
    "warehouse/hooks.py": "a9b2fc0f94136cdc65a63b48b4186c65798360f498c16d4aa497adf9fae87799",
    "warehouse/operators.py": "8c642d9c439ab0cc52bc41b00b3458f8f6b8ec9b4d3688ebffb1b80615acdc42",
}


@pytest.mark.parametrize("rel", sorted(REVIEWED))
def test_dag_source_matches_reviewed_version(rel):
    digest = hashlib.sha256((DAGS_DIR / rel).read_bytes()).hexdigest()
    assert digest == REVIEWED[rel], f"{rel} changed since review"
