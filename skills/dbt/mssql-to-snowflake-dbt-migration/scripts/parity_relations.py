#!/usr/bin/env python3
"""Emit one relation_name per line for every migrated node — fed to
altimate-code's data-parity prompt.

Resolves relation_name via `target/manifest.json` (works on all dbt-core
versions, including 1.7 where run_results.json omits relation_name).

Hard-stops if the output is empty — downstream parity won't run on
nothing.

Environment: none required (reads target/manifest.json + run_results.json).
"""
from __future__ import annotations

import json
import pathlib
import sys


def main() -> int:
    manifest_path = pathlib.Path("target/manifest.json")
    rr_path = pathlib.Path("target/run_results.json")
    if not manifest_path.exists() or not rr_path.exists():
        print(
            "parity_relations.py: target/manifest.json or run_results.json missing",
            file=sys.stderr,
        )
        return 1

    manifest = json.loads(manifest_path.read_text())
    rr = json.loads(rr_path.read_text())
    nodes = manifest.get("nodes", {})

    emitted = 0
    for r in rr.get("results", []):
        uid = r.get("unique_id") or ""
        if not uid.startswith("model."):
            continue
        node = nodes.get(uid) or {}
        rel = node.get("relation_name") or r.get("relation_name")
        if not rel:
            db = node.get("database")
            sch = node.get("schema")
            alias = node.get("alias") or node.get("name")
            if db and sch and alias:
                rel = f'"{db}"."{sch}"."{alias}"'
        if rel:
            print(rel)
            emitted += 1

    if emitted == 0:
        print(
            "parity_relations.py: zero model results — did Phase 5 build anything?",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
