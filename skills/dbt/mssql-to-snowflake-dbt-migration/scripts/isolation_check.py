#!/usr/bin/env python3
"""Isolation check: every migrated node's materialised schema must start
with ISOLATED_SCHEMA_PREFIX.

Reads selected unique_ids from `target/run_results.json`
(top-level `unique_id` is version-stable across dbt-core 1.5+), then
looks each one up in `target/manifest.json` for the authoritative
`relation_name` (`relation_name` in run_results.json is only present
from dbt-core 1.8, but in manifest.json it is present from parse time
on every supported version).

Exits non-zero on:
  - empty ISOLATED_SCHEMA_PREFIX  (fail-closed on bad state)
  - zero models checked           (empty-check silent pass)
  - any node outside the prefix

Environment:
  ISOLATED_SCHEMA_PREFIX   required (from state.sh load)
"""
from __future__ import annotations

import json
import os
import pathlib
import sys


def main() -> int:
    prefix = os.environ.get("ISOLATED_SCHEMA_PREFIX", "")
    if not prefix:
        print(
            "isolation_check.py: ISOLATED_SCHEMA_PREFIX is empty — "
            "did state.sh load run?",
            file=sys.stderr,
        )
        return 1
    prefix_u = prefix.upper()

    manifest_path = pathlib.Path("target/manifest.json")
    rr_path = pathlib.Path("target/run_results.json")
    if not manifest_path.exists():
        print(f"isolation_check.py: {manifest_path} missing", file=sys.stderr)
        return 1
    if not rr_path.exists():
        print(f"isolation_check.py: {rr_path} missing", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text())
    rr = json.loads(rr_path.read_text())
    nodes = manifest.get("nodes", {})

    checked = 0
    offenders: list[tuple[str, str, str]] = []

    # BUILDABLE here matches what `dbt build` materialises with a schema.
    BUILDABLE_PREFIXES = ("model.", "snapshot.", "seed.")

    for r in rr.get("results", []):
        uid = r.get("unique_id") or ""
        if not any(uid.startswith(p) for p in BUILDABLE_PREFIXES):
            continue
        node = nodes.get(uid) or {}
        # Prefer manifest.json relation_name (version-stable);
        # fall back to run_results.json if the manifest entry is missing.
        rel = node.get("relation_name") or r.get("relation_name") or ""
        if not rel:
            db = node.get("database")
            sch = node.get("schema")
            alias = node.get("alias") or node.get("name")
            if db and sch and alias:
                rel = f'"{db}"."{sch}"."{alias}"'
        if not rel:
            offenders.append((uid, "", "no relation_name resolvable"))
            continue
        bare = rel.replace('"', "").upper()
        parts = bare.split(".")
        if len(parts) < 3:
            offenders.append((uid, rel, f"unparseable relation {rel!r}"))
            continue
        schema = parts[1]
        if not schema.startswith(prefix_u):
            offenders.append(
                (uid, rel, f"schema {schema!r} does not start with {prefix!r}")
            )
        checked += 1

    if checked == 0:
        print(
            "isolation_check.py: zero model/snapshot/seed results in "
            "run_results.json — nothing to check",
            file=sys.stderr,
        )
        return 1

    if offenders:
        print(
            "Isolation check FAILED — the following landed outside the "
            "isolated prefix:",
            file=sys.stderr,
        )
        for uid, rel, why in offenders:
            print(f"  - {uid}: {rel}  ({why})", file=sys.stderr)
        return 1

    print(f"Isolation check PASS — all {checked} resource(s) under {prefix}*.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
