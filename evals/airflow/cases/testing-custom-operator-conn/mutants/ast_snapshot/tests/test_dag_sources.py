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
    'load_raw_sales.py': '1258cfcf81705234fca893c1d5d1ce11382c68778f4d719b66751b0c455afbae',
    'warehouse/__init__.py': '3d8c9237b838785019b7ebfbc7f3a5694c298cbcae817d6061dd37bc53857a00',
    'warehouse/hooks.py': 'fc003b88ff0b2af524864d7ea0b44fe367570197c63484897397bc74740a22dd',
    'warehouse/operators.py': '5752d2c03447620e7a94f9dfc2b26feb7837e93d126e34724bad2f5d0715f65b',
}


def _ast_digest(path: Path) -> str:
    return hashlib.sha256(ast.dump(ast.parse(path.read_text())).encode()).hexdigest()


@pytest.mark.parametrize("rel", sorted(REVIEWED))
def test_dag_code_matches_reviewed_version(rel):
    assert _ast_digest(DAGS_DIR / rel) == REVIEWED[rel], f"{rel} changed since review"
