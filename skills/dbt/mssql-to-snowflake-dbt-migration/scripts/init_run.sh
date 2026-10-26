#!/usr/bin/env bash
# init_run.sh — Phase 4: initialise run state + confirm layering.
# Sets TS, ISOLATED_SCHEMA_PREFIX, LAYERING, SCOPE_SELECTOR, REPO_ROOT,
# DBT_ROOT.
#
# Usage: scripts/init_run.sh <layering> <scope_selector> <dbt_root>
#   layering          Medallion | DataVault
#   scope_selector    comma-separated dbt --select set, e.g. "stg_sales int_sales fct_sales"
#   dbt_root          repo-root-relative path to the dbt project (e.g. ".")

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/state.sh" init

LAYERING="${1:?layering required}"
SCOPE_SELECTOR="${2:?scope selector required}"
DBT_ROOT="${3:-.}"

case "$LAYERING" in
  Medallion|DataVault) ;;
  *) echo "init_run.sh: unknown layering '$LAYERING' (Medallion|DataVault)" >&2; exit 1 ;;
esac

REPO_ROOT="$(git rev-parse --show-toplevel)"
TS="$(date +%Y%m%d_%H%M%S)"
ISOLATED_SCHEMA_PREFIX="MIGRATION_${TS}"

source "$HERE/state.sh" set REPO_ROOT "$REPO_ROOT"
source "$HERE/state.sh" set DBT_ROOT "$DBT_ROOT"
source "$HERE/state.sh" set TS "$TS"
source "$HERE/state.sh" set ISOLATED_SCHEMA_PREFIX "$ISOLATED_SCHEMA_PREFIX"
source "$HERE/state.sh" set LAYERING "$LAYERING"
source "$HERE/state.sh" set SCOPE_SELECTOR "$SCOPE_SELECTOR"

echo "Run initialised: TS=$TS  PREFIX=$ISOLATED_SCHEMA_PREFIX  LAYERING=$LAYERING  SELECTOR=$SCOPE_SELECTOR"
