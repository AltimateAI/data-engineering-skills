#!/usr/bin/env bash
# deploy_isolated.sh — Phase 5: deploy migrated models to the isolated
# schema (never prod) and verify via manifest.
#
# Usage: scripts/deploy_isolated.sh {method1|method2} [<non_prod_target>]

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/state.sh" load
# shellcheck disable=SC1091
source "$HERE/state.sh" validate REPO_ROOT DBT_ROOT TS ISOLATED_SCHEMA_PREFIX SCOPE_SELECTOR

METHOD="${1:?method1|method2 required}"
NON_PROD_TARGET="${2:-${DBT_NONPROD_TARGET:-migration}}"

cd "$REPO_ROOT/$DBT_ROOT"
dbt deps >/dev/null 2>&1 || true

case "$METHOD" in
  method1)
    # profiles.yml must have `schema: "{{ env_var('DBT_SCHEMA') }}"` under
    # a dedicated target. See SKILL.md Phase 5 Method 1.
    export DBT_SCHEMA="$ISOLATED_SCHEMA_PREFIX"
    dbt build \
      --select "$SCOPE_SELECTOR" \
      --target "$NON_PROD_TARGET" \
      --fail-fast
    ;;
  method2)
    # Requires a custom generate_schema_name macro that reads
    # var('target_schema'). SKILL.md documents how to verify it exists.
    dbt build \
      --select "$SCOPE_SELECTOR" \
      --target "$NON_PROD_TARGET" \
      --vars "{target_schema: \"${ISOLATED_SCHEMA_PREFIX}\"}" \
      --fail-fast
    ;;
  *)
    echo "deploy_isolated.sh: unknown method '$METHOD' (method1|method2)" >&2
    exit 1
    ;;
esac

# Isolation check — authoritative, from the manifest (not run_results.json,
# which doesn't have relation_name on dbt 1.7).
python3 "$HERE/isolation_check.py"
