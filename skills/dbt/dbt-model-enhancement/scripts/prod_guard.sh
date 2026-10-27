#!/usr/bin/env bash
# prod_guard.sh — resolve selector, denylist-check every selected uid's
# relation_name via manifest.json, then build with the SAME selector and
# target. One invocation = guard and build cannot diverge.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
if ! source "$SCRIPT_DIR/state.sh" load 2>/dev/null; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/state.sh" init
fi

SELECTOR="${1:?selector required (e.g. '<model>+')}"
: "${DBT_PROD_DENYLIST:?Set DBT_PROD_DENYLIST (e.g. 'ANALYTICS_PROD|ANALYTICS.MARTS') — refusing by default}"
NON_PROD_TARGET="${DBT_NONPROD_TARGET:-dev}"

case "$(printf '%s' "$NON_PROD_TARGET" | tr '[:upper:]' '[:lower:]')" in
  prod|production|prd|live)
    echo "prod_guard.sh: target name '$NON_PROD_TARGET' looks like production — refusing" >&2
    exit 1
    ;;
esac

dbt deps >/dev/null 2>&1 || true
dbt parse --target "$NON_PROD_TARGET" --quiet >/dev/null \
  || { echo "prod_guard.sh: dbt parse failed for target '$NON_PROD_TARGET'" >&2; exit 1; }

export SELECTOR DBT_PROD_DENYLIST NON_PROD_TARGET DBT_STATE_DIR

python3 - <<'PY'
import json, os, pathlib, re, subprocess, sys

selector = os.environ["SELECTOR"]
denylist_raw = os.environ["DBT_PROD_DENYLIST"]
target = os.environ["NON_PROD_TARGET"]
state_dir = os.environ.get("DBT_STATE_DIR", "")

ls_cmd = ["dbt", "ls", "--target", target, "--select", selector, "--output", "json"]
if state_dir:
    ls_cmd += ["--state", state_dir]
ls = subprocess.run(ls_cmd, capture_output=True, text=True)
if ls.returncode != 0:
    sys.exit(f"dbt ls failed: {ls.stderr.strip() or ls.stdout.strip()}")

BUILDABLE_PREFIXES = ("model.", "snapshot.", "seed.")
unique_ids = []
for line in ls.stdout.splitlines():
    try:
        node = json.loads(line)
    except Exception:
        continue
    uid = node.get("unique_id") or ""
    if any(uid.startswith(p) for p in BUILDABLE_PREFIXES):
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
        db = node.get("database"); sch = node.get("schema"); alias = node.get("alias") or node.get("name")
        if db and sch and alias:
            rel = f'"{db}"."{sch}"."{alias}"'
    if rel:
        selected_rels.append((uid, rel))
if not selected_rels:
    sys.exit("Could not resolve any relation_name from manifest.json.")

denylist = [d.strip().upper() for d in re.split(r"[,|]", denylist_raw) if d.strip()]
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

dbt debug --target "$NON_PROD_TARGET" >/dev/null \
  || { echo "prod_guard.sh: cannot connect with target '$NON_PROD_TARGET'" >&2; exit 1; }

EXTRA=()
if [ -n "${DBT_STATE_DIR:-}" ]; then
  EXTRA=(--defer --state "$DBT_STATE_DIR")
fi
dbt build --select "$SELECTOR" --target "$NON_PROD_TARGET" ${EXTRA[@]+"${EXTRA[@]}"} --fail-fast

# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" set NON_PROD_TARGET "$NON_PROD_TARGET"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" set APPROVED_SELECTOR "$SELECTOR"
