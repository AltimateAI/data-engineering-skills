"""Golden-file regression guard: fail CI when any DAG source drifts from the reviewed version."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"
REVIEWED = {
    "customer_snapshot.py": "b95530fd787b8316036d341675c74d52d2da715d7400c5a137b97d696fe0d0e6",
    "marketing_spend.py": "9c2ab57505a057eb4ab9a143b4b316f60881a8d4ff123ba721ed664105dbfa7b",
    "orders_ingest.py": "caee1cca563572392e2b7c94f8f6726dff1448caa2965c0cd11685730c27dbed",
}


@pytest.mark.parametrize("rel", sorted(REVIEWED))
def test_dag_source_matches_reviewed_version(rel):
    digest = hashlib.sha256((DAGS_DIR / rel).read_bytes()).hexdigest()
    assert digest == REVIEWED[rel], f"{rel} changed since review"
