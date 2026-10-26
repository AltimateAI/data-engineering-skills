#!/usr/bin/env python3
"""Smoke test for mssql isolation_check.py — covers the three cases:

1. Empty ISOLATED_SCHEMA_PREFIX → fail-closed (exit 1).
2. A leaked model landing outside the prefix → exit 1 with offender named.
3. All models under the prefix (incl. +schema suffixes) → PASS exit 0.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).parent.resolve()
REPO = HERE.parent.parent
SCRIPT = REPO / "skills/dbt/mssql-to-snowflake-dbt-migration/scripts/isolation_check.py"
if not SCRIPT.exists():
    sys.exit(f"missing {SCRIPT}")


def run(prefix, nodes, results, env_extra=None):
    """Run isolation_check.py against a mock target/ dir."""
    env = dict(os.environ)
    env["ISOLATED_SCHEMA_PREFIX"] = prefix
    if env_extra:
        env.update(env_extra)
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        (tdp / "target").mkdir()
        (tdp / "target/manifest.json").write_text(json.dumps({"nodes": nodes}))
        (tdp / "target/run_results.json").write_text(json.dumps({"results": results}))
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=td, env=env, capture_output=True, text=True,
        )


# Test 1: empty prefix → fail-closed
r = run(
    prefix="",
    nodes={"model.proj.foo": {"relation_name": '"DB"."SCHEMA"."FOO"'}},
    results=[{"unique_id": "model.proj.foo"}],
)
assert r.returncode == 1, f"empty-prefix test: expected rc=1 got {r.returncode}, stderr={r.stderr}"
assert "empty" in r.stderr.lower() or "prefix" in r.stderr.lower()
print("test 1 (empty prefix) PASS")

# Test 2: leaked model → fail with offender named
r = run(
    prefix="MIGRATION_20261026",
    nodes={
        "model.proj.good": {"relation_name": '"DB"."MIGRATION_20261026_BRONZE"."GOOD"'},
        "model.proj.bad":  {"relation_name": '"DB"."OTHER_SCHEMA"."BAD"'},
    },
    results=[
        {"unique_id": "model.proj.good"},
        {"unique_id": "model.proj.bad"},
    ],
)
assert r.returncode == 1, f"leak test: expected rc=1 got {r.returncode}"
assert "model.proj.bad" in r.stderr, f"leak test: offender not named: {r.stderr}"
print("test 2 (leaked model) PASS")

# Test 3: all under prefix → PASS
r = run(
    prefix="MIGRATION_20261026",
    nodes={
        "model.proj.bronze": {"relation_name": '"DB"."MIGRATION_20261026_BRONZE"."B"'},
        "model.proj.silver": {"relation_name": '"DB"."MIGRATION_20261026_SILVER"."S"'},
        "model.proj.gold":   {"relation_name": '"DB"."MIGRATION_20261026_GOLD"."G"'},
    },
    results=[
        {"unique_id": "model.proj.bronze"},
        {"unique_id": "model.proj.silver"},
        {"unique_id": "model.proj.gold"},
    ],
)
assert r.returncode == 0, f"all-under test: expected rc=0 got {r.returncode}, stderr={r.stderr}"
assert "PASS" in r.stdout, f"all-under test: no PASS in stdout: {r.stdout}"
print("test 3 (all under prefix) PASS")

# Test 4: zero model results → hard-stop (not silent pass)
r = run(
    prefix="MIGRATION_20261026",
    nodes={},
    results=[{"unique_id": "test.proj.not_a_model"}],
)
assert r.returncode == 1, f"zero-model test: expected rc=1 got {r.returncode}"
print("test 4 (zero model results) PASS")

print("\nisolation_check: all 4 tests PASS")
