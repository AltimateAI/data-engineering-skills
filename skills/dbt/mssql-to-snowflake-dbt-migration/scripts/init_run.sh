#!/usr/bin/env bash
# init_run.sh — Phase 0: initialise run state + record the layering
# choice. Must run from the skill directory.
#
# Usage: scripts/init_run.sh <layering> <scope_selector> <dbt_root>
#   layering          Medallion | DataVault
#   scope_selector    SPACE-separated dbt --select set, e.g.
#                     "stg_sales int_sales fct_sales". Commas are NOT
#                     union — in dbt they're intersection.
#   dbt_root          repo-root-relative path to the dbt project (e.g.
#                     ".", "transform", "dbt/")
#
# This script does NOT accept --force; call `scripts/state.sh reset`
# first if a stale run exists.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" init

LAYERING="${1:?layering required (Medallion|DataVault)}"
SCOPE_SELECTOR_RAW="${2:?scope selector required}"
DBT_ROOT_IN="${3:-.}"

case "$LAYERING" in
  Medallion|DataVault) ;;
  *) echo "init_run.sh: unknown layering '$LAYERING' (Medallion|DataVault)" >&2; exit 1 ;;
esac

# Normalise selector: convert any commas to spaces (dbt treats comma as
# intersection; the user almost certainly meant union). Collapse runs
# of whitespace.
SCOPE_SELECTOR="$(printf '%s' "$SCOPE_SELECTOR_RAW" | tr ',' ' ' | tr -s '[:space:]' ' ')"
SCOPE_SELECTOR="${SCOPE_SELECTOR# }"
SCOPE_SELECTOR="${SCOPE_SELECTOR% }"

REPO_ROOT="$(git rev-parse --show-toplevel)"
TS="$(date +%Y%m%d_%H%M%S)"
ISOLATED_SCHEMA_PREFIX="MIGRATION_${TS}"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" set REPO_ROOT              "$REPO_ROOT"
source "$SCRIPT_DIR/state.sh" set SKILL_DIR              "$SKILL_DIR"
source "$SCRIPT_DIR/state.sh" set DBT_ROOT               "$DBT_ROOT_IN"
source "$SCRIPT_DIR/state.sh" set TS                     "$TS"
source "$SCRIPT_DIR/state.sh" set ISOLATED_SCHEMA_PREFIX "$ISOLATED_SCHEMA_PREFIX"
source "$SCRIPT_DIR/state.sh" set LAYERING               "$LAYERING"
source "$SCRIPT_DIR/state.sh" set SCOPE_SELECTOR         "$SCOPE_SELECTOR"

echo "Run initialised: TS=$TS  PREFIX=$ISOLATED_SCHEMA_PREFIX  LAYERING=$LAYERING  SELECTOR='$SCOPE_SELECTOR'"
