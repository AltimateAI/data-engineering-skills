#!/usr/bin/env bash
# prod_guard.sh — resolve the --select set via dbt ls, look each node's
# relation_name up in target/manifest.json, and refuse if any resolves
# to a DBT_PROD_DENYLIST entry. Then run `dbt build` with the SAME
# selector and target in the same invocation, so the guard and build
# can't diverge.
#
# Usage: scripts/prod_guard.sh <selector>
#   env:  DBT_NONPROD_TARGET  (default: dev)
#         DBT_PROD_DENYLIST   (REQUIRED — fail-closed)
#         DBT_STATE_DIR       (optional — enables --defer --state)

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/state.sh" load
# shellcheck disable=SC1091
source "$HERE/state.sh" validate REPO_ROOT DBT_ROOT

SELECTOR="${1:?selector required (e.g. '+<model>')}"

: "${DBT_PROD_DENYLIST:?Set DBT_PROD_DENYLIST (e.g. 'ANALYTICS_PROD|ANALYTICS.MARTS') — refusing by default}"
NON_PROD_TARGET="${DBT_NONPROD_TARGET:-dev}"

# Target name check — refuse prod-looking names.
case "$(printf %s "$NON_PROD_TARGET" | tr '[:upper:]' '[:lower:]')" in
  prod|production|prd|live)
    echo "prod_guard.sh: target name '$NON_PROD_TARGET' looks like production — refusing" >&2
    exit 1
    ;;
esac

cd "$REPO_ROOT/$DBT_ROOT"

# Install packages before any dbt invocation.
dbt deps >/dev/null 2>&1 || true
dbt parse --target "$NON_PROD_TARGET" --quiet >/dev/null \
  || { echo "prod_guard.sh: dbt parse failed for target '$NON_PROD_TARGET'" >&2; exit 1; }

# The guard checks EVERY buildable resource (model, snapshot, seed),
# not just models — `dbt build --select <selector>` runs them too.
export SELECTOR DBT_PROD_DENYLIST NON_PROD_TARGET DBT_STATE_DIR

python3 - <<'PY'
import json, os, pathlib, re, subprocess, sys

selector = os.environ["SELECTOR"]
denylist_raw = os.environ["DBT_PROD_DENYLIST"]
target = os.environ["NON_PROD_TARGET"]
state_dir = os.environ.get("DBT_STATE_DIR", "")

# If a `state:*` selector is used (e.g. state:modified+), `dbt ls` and
# `dbt build` both need --state. Pass it to `dbt ls` here so the
# selector resolves; `dbt build` below also passes it.
ls_cmd = ["dbt", "ls", "--target", target, "--select", selector, "--output", "json"]
if state_dir:
    ls_cmd += ["--state", state_dir]

ls = subprocess.run(ls_cmd, capture_output=True, text=True)
if ls.returncode != 0:
    sys.exit(f"dbt ls failed: {ls.stderr.strip() or ls.stdout.strip()}")

unique_ids = []
# dbt build runs model, snapshot, seed, test (for stored failures).
# relation_name is written at parse time for anything with a materialised
# relation — that's model, snapshot, seed. Tests go through store_failures.
BUILDABLE = {"model", "snapshot", "seed"}
for line in ls.stdout.splitlines():
    try:
        node = json.loads(line)
    except Exception:
        continue
    uid = node.get("unique_id") or ""
    rtype = (uid.split(".", 1)[0] or "").lower() if uid else ""
    if rtype in BUILDABLE:
        unique_ids.append(uid)

if not unique_ids:
    sys.exit(f"No buildable resources matched selector {selector!r} on target {target!r}.")

manifest_path = pathlib.Path("target/manifest.json")
if not manifest_path.exists():
    sys.exit("target/manifest.json missing — did `dbt parse` run?")
manifest = json.loads(manifest_path.read_text())
nodes = manifest.get("nodes", {})

selected_rels = []
for uid in unique_ids:
    node = nodes.get(uid) or {}
    rel = node.get("relation_name")
    if not rel:
        # Snapshots / seeds sometimes have relation_name NULL in older dbt.
        # Reconstruct from database/schema/alias if present.
        db = node.get("database"); sch = node.get("schema"); alias = node.get("alias") or node.get("name")
        if db and sch and alias:
            rel = f'"{db}"."{sch}"."{alias}"'
    if rel:
        selected_rels.append((uid, rel))

if not selected_rels:
    sys.exit("Could not resolve any relation_name from manifest.json.")

denylist = [
    d.strip().upper()
    for d in re.split(r"[,|]", denylist_raw)
    if d.strip()
]
if not denylist:
    sys.exit("DBT_PROD_DENYLIST is set but empty after parsing.")

offenders = []
for uid, rel in selected_rels:
    bare = rel.replace('"', '').upper()
    for denied in denylist:
        if bare == denied or bare.startswith(denied + "."):
            offenders.append((uid, rel, denied))
            break

if offenders:
    for uid, rel, denied in offenders:
        print(f"Refusing: {uid} resolves to {rel} (denied: {denied})", file=sys.stderr)
    sys.exit(1)

print(f"Non-prod guard PASS — {len(selected_rels)} resource(s) checked against denylist.")
PY

# Connection check (last).
dbt debug --target "$NON_PROD_TARGET" >/dev/null \
  || { echo "prod_guard.sh: cannot connect with target '$NON_PROD_TARGET'" >&2; exit 1; }

# Build with the SAME selector + target the guard just verified.
# bash 3.2 (macOS /bin/bash) under `set -u` rejects "${EXTRA[@]}" when
# EXTRA is empty, so guard the expansion with the ${EXTRA[@]+...} form.
EXTRA=()
if [ -n "${DBT_STATE_DIR:-}" ]; then
  EXTRA=(--defer --state "$DBT_STATE_DIR")
fi

dbt build --select "$SELECTOR" --target "$NON_PROD_TARGET" ${EXTRA[@]+"${EXTRA[@]}"} --fail-fast

# Persist the approved target so later phases can reference it.
source "$HERE/state.sh" set NON_PROD_TARGET "$NON_PROD_TARGET"
source "$HERE/state.sh" set APPROVED_SELECTOR "$SELECTOR"
