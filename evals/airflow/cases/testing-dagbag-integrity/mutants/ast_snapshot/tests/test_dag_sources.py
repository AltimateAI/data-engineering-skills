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
    'customer_snapshot.py': '700c38701f2408558b66c95b5b230ae7435688a229422f43ac4bdbaab0a344d4',
    'marketing_spend.py': '65b8b329717e530fa461f52660e577681c28fb2dc6ab3f9f4c5d50d8d35261a1',
    'orders_ingest.py': '3e542e10fe7b98e5550e1bb446ec98a8f983ebb27c54abb8382d6d9f9547d0c1',
}


def _ast_digest(path: Path) -> str:
    return hashlib.sha256(ast.dump(ast.parse(path.read_text())).encode()).hexdigest()


@pytest.mark.parametrize("rel", sorted(REVIEWED))
def test_dag_code_matches_reviewed_version(rel):
    assert _ast_digest(DAGS_DIR / rel) == REVIEWED[rel], f"{rel} changed since review"
