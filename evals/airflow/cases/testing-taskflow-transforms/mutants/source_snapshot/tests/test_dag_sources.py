"""Golden-file regression guard: fail CI when any DAG source drifts from the reviewed version."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"
REVIEWED = {
    "orders_enrichment.py": "5e1a3e2d63741f149fae528b9f1ea7d97ab9e55f80d8a7962d32f8dec58b0d53",
}


@pytest.mark.parametrize("rel", sorted(REVIEWED))
def test_dag_source_matches_reviewed_version(rel):
    digest = hashlib.sha256((DAGS_DIR / rel).read_bytes()).hexdigest()
    assert digest == REVIEWED[rel], f"{rel} changed since review"
