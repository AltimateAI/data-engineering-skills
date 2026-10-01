"""Golden-AST regression guard: fail CI when the code of any DAG file changes.

Comments and formatting are ignored (the AST is compared), so reformatting or
documenting a DAG does not trip it; any change to the code does.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"
REVIEWED = {
    'carrier_rates_weekly.py': 'c08ee1337c0d8b93fa8ad91212a0004566728bedb653e34727c30733d75091b6',
    'shipments_daily.py': '4369df7c09e17570488670e0628fd4da893eec945c5ab8070e090e3ead7d9adc',
}


def _ast_digest(path: Path) -> str:
    return hashlib.sha256(ast.dump(ast.parse(path.read_text())).encode()).hexdigest()


@pytest.mark.parametrize("rel", sorted(REVIEWED))
def test_dag_code_matches_reviewed_version(rel):
    assert _ast_digest(DAGS_DIR / rel) == REVIEWED[rel], f"{rel} changed since review"
