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
    'orders_enrichment.py': 'fb6192350ad469b55db8ed239dbc3d7b05b828d9c865ea1533c12d1840ee5e5d',
}


def _ast_digest(path: Path) -> str:
    return hashlib.sha256(ast.dump(ast.parse(path.read_text())).encode()).hexdigest()


@pytest.mark.parametrize("rel", sorted(REVIEWED))
def test_dag_code_matches_reviewed_version(rel):
    assert _ast_digest(DAGS_DIR / rel) == REVIEWED[rel], f"{rel} changed since review"
