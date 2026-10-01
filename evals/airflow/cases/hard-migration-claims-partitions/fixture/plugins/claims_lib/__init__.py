"""Shared code for the claims DAGs (on sys.path via the plugins folder)."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAKE = PROJECT_ROOT / "output" / "lake"
MARTS = PROJECT_ROOT / "output" / "marts"
