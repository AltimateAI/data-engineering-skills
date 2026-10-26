#!/usr/bin/env bash
# deploy_isolated.sh — Phase 5: deploy migrated models to the isolated
# schema (never prod) and verify via manifest.
#
# Pre-build gates (both methods):
#   - DBT_PROD_DENYLIST must be set (fail-closed).
#   - Target name is not prod/production/prd/live.
#   - A dry-run `dbt compile` with the isolation env/vars confirms that
#     every migrated node's compiled relation lands in
#     $ISOLATED_SCHEMA_PREFIX*. If any node compiles to a non-prefix
#     schema (e.g. Method 2 without the generate_schema_name macro),
#     refuse before any write.
#   - A target denylist check mirrors prod_guard.sh's approach.
#
# Post-build:
#   - Isolation check runs even if `dbt build` fails (trap-based), so
#     partial writes are reported.
#
# Usage: scripts/deploy_isolated.sh {method1|method2} [<non_prod_target>]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" load
# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" validate REPO_ROOT DBT_ROOT TS ISOLATED_SCHEMA_PREFIX SCOPE_SELECTOR

METHOD="${1:?method1|method2 required}"
NON_PROD_TARGET="${2:-${DBT_NONPROD_TARGET:-migration}}"

: "${DBT_PROD_DENYLIST:?Set DBT_PROD_DENYLIST (e.g. 'ANALYTICS_PROD|ANALYTICS.MARTS') — refusing by default}"

case "$(printf '%s' "$NON_PROD_TARGET" | tr '[:upper:]' '[:lower:]')" in
  prod|production|prd|live)
    echo "deploy_isolated.sh: target name '$NON_PROD_TARGET' looks like production — refusing" >&2
    exit 1
    ;;
esac

cd "$REPO_ROOT/$DBT_ROOT"
dbt deps >/dev/null 2>&1 || true

# For Method 2, verify the custom generate_schema_name macro exists —
# otherwise `--vars target_schema` is a no-op and the build silently
# lands in the default schema.
if [ "$METHOD" = "method2" ]; then
  if ! grep -rln 'generate_schema_name' macros/ 2>/dev/null | head -1 >/dev/null; then
    echo "deploy_isolated.sh: method2 requires a custom generate_schema_name macro" >&2
    echo "  in macros/, but none was found. Either add it or use method1." >&2
    exit 1
  fi
fi

# ---- Dry-run gate: parse + confirm compiled relations hit the prefix ----
# Set the schema env/var the same way the real build will, then parse
# and read the resulting manifest.json. If any migrated node's
# relation_name doesn't start with $ISOLATED_SCHEMA_PREFIX, refuse.
case "$METHOD" in
  method1) export DBT_SCHEMA="$ISOLATED_SCHEMA_PREFIX" ;;
  method2) : ;;  # --vars is passed on both parse + build below
esac

PARSE_ARGS=(--target "$NON_PROD_TARGET")
if [ "$METHOD" = "method2" ]; then
  PARSE_ARGS+=(--vars "{target_schema: \"${ISOLATED_SCHEMA_PREFIX}\"}")
fi
dbt parse "${PARSE_ARGS[@]}" --quiet >/dev/null \
  || { echo "deploy_isolated.sh: dbt parse failed before build" >&2; exit 1; }

# Pre-build isolation check against the parsed manifest.
export ISOLATED_SCHEMA_PREFIX SCOPE_SELECTOR DBT_PROD_DENYLIST
python3 - <<'PY'
import json, os, pathlib, re, sys

prefix = os.environ["ISOLATED_SCHEMA_PREFIX"].upper()
selector = os.environ["SCOPE_SELECTOR"].strip()
denylist_raw = os.environ["DBT_PROD_DENYLIST"]
denylist = [d.strip().upper() for d in re.split(r"[,|]", denylist_raw) if d.strip()]

mani = pathlib.Path("target/manifest.json")
if not mani.exists():
    sys.exit("target/manifest.json missing after dbt parse")
manifest = json.loads(mani.read_text())

# Match on the SCOPE_SELECTOR's space-separated model NAMES. This is a
# coarse pre-build check; the real selector resolution happens in `dbt
# build`. We're confirming that EVERY node matching our selector has a
# compiled relation under the prefix.
scope_names = set(selector.split())
if not scope_names:
    sys.exit("SCOPE_SELECTOR is empty")

offenders_prefix = []
offenders_denylist = []
checked = 0
for uid, node in manifest.get("nodes", {}).items():
    if not (uid.startswith("model.") or uid.startswith("snapshot.") or uid.startswith("seed.")):
        continue
    name = node.get("name", "")
    if name not in scope_names:
        continue
    rel = node.get("relation_name") or ""
    rel_u = rel.replace('"', '').upper()
    if not rel_u:
        offenders_prefix.append((uid, "", "no relation_name in manifest"))
        continue
    parts = rel_u.split(".")
    if len(parts) < 3:
        offenders_prefix.append((uid, rel, f"unparseable relation {rel!r}"))
        continue
    schema = parts[1]
    # Prefix check: must land in MIGRATION_<ts>*
    if not schema.startswith(prefix):
        offenders_prefix.append((uid, rel, f"schema {schema!r} does not start with {prefix!r}"))
    # Denylist check: must not resolve to a denied database or db.schema
    bare = ".".join(parts[0:2])  # DB.SCHEMA
    for denied in denylist:
        if bare == denied or parts[0] == denied or bare.startswith(denied + "."):
            offenders_denylist.append((uid, rel, denied))
            break
    checked += 1

if checked == 0:
    sys.exit(f"Pre-build check: 0 models matched SCOPE_SELECTOR ({selector!r}) in manifest — refusing")

if offenders_prefix or offenders_denylist:
    if offenders_prefix:
        print("Pre-build FAIL — these models would land outside the isolated prefix:", file=sys.stderr)
        for uid, rel, why in offenders_prefix:
            print(f"  - {uid}: {rel}  ({why})", file=sys.stderr)
    if offenders_denylist:
        print("Pre-build FAIL — these models would land in a denied prod location:", file=sys.stderr)
        for uid, rel, denied in offenders_denylist:
            print(f"  - {uid}: {rel}  (denied: {denied})", file=sys.stderr)
    sys.exit(1)

print(f"Pre-build gate PASS — {checked} resource(s) will land under {prefix}* and clear of the denylist.")
PY

# ---- Build + mandatory post-build isolation check (even on failure) ----
BUILD_ARGS=(--select "$SCOPE_SELECTOR" --target "$NON_PROD_TARGET" --fail-fast)
if [ "$METHOD" = "method2" ]; then
  BUILD_ARGS+=(--vars "{target_schema: \"${ISOLATED_SCHEMA_PREFIX}\"}")
fi

build_rc=0
# Run isolation_check even if dbt build fails (partial writes). Use a
# subshell + explicit rc capture so `set -e` doesn't abort on a non-zero
# dbt build, and we can STILL run the post-build check.
set +e
dbt build "${BUILD_ARGS[@]}"
build_rc=$?
set -e

# Isolation check — authoritative, reads target/manifest.json by
# unique_id from run_results.json. Runs even if the build failed.
python3 "$SCRIPT_DIR/isolation_check.py"
isolation_rc=$?

if [ $build_rc -ne 0 ]; then
  echo "deploy_isolated.sh: dbt build failed (rc=$build_rc). Isolation check status: $isolation_rc." >&2
  exit $build_rc
fi
if [ $isolation_rc -ne 0 ]; then
  exit $isolation_rc
fi
