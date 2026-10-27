#!/usr/bin/env bash
# detect_env.sh — Phase 2 environment detection.
#
# Resolves + persists:
#   REPO_ROOT, DBT_ROOT, ORCHESTRATOR, AIRFLOW_DAGS_DIR, GH_AUTH_OK,
#   PIPELINE_NAME (validated), SKILL_DIR (absolute).
#
# Usage: scripts/detect_env.sh <pipeline_name>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---- Validate all inputs BEFORE touching state ------------------------
# `state.sh init` creates a `current_run` pointer and now refuses a
# second init without --force. If we init first and then die on bad
# input, every retry hits "a run is already active". Validate everything
# we can up front, so a typo'd pipeline name or an ambiguous dbt
# project doesn't leave a stale run behind.

PIPELINE_NAME_RAW="${1:-}"
if [ -z "$PIPELINE_NAME_RAW" ]; then
  echo "detect_env.sh: pipeline name required (arg 1)" >&2
  exit 1
fi

if ! printf '%s' "$PIPELINE_NAME_RAW" | grep -qE '^[a-z][a-z0-9_]{0,63}$'; then
  echo "detect_env.sh: invalid pipeline name '$PIPELINE_NAME_RAW'" >&2
  echo "  must match ^[a-z][a-z0-9_]{0,63}\$" >&2
  exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"

# --- dbt project (shallowest, excluding dbt_packages/ and target/) ---
# Search with cwd=REPO_ROOT and relative paths, so repos under hidden
# parent directories (e.g. ~/.worktrees/proj) aren't excluded by
# `-not -path '*/.*'`.
cd "$REPO_ROOT"
# Depth is the number of path separators in the match. Use NF as the
# length counter but preserve the ENTIRE path (which may contain spaces)
# by stripping the leading field count instead of printing $2.
dbt_candidates="$(
  find . -maxdepth 4 -name dbt_project.yml \
    -not -path '*/dbt_packages/*' \
    -not -path '*/target/*' 2>/dev/null \
  | awk -F/ '{printf "%d\t%s\n", NF, $0}' \
  | sort -n
)"
shallowest_depth="$(printf '%s\n' "$dbt_candidates" | head -1 | awk -F'\t' '{print $1}')"
shallowest_hits="$(printf '%s\n' "$dbt_candidates" | awk -F'\t' -v d="$shallowest_depth" '$1==d {print $2}')"
shallowest_count="$(printf '%s\n' "$shallowest_hits" | grep -c . || true)"

if [ -z "$shallowest_hits" ]; then
  echo "detect_env.sh: no dbt_project.yml found" >&2
  exit 1
fi
if [ "$shallowest_count" -gt 1 ]; then
  echo "detect_env.sh: multiple dbt_project.yml at shallowest depth:" >&2
  # shellcheck disable=SC2086  # intentional word-split: one path per line
  printf '  %s\n' $shallowest_hits >&2
  exit 1
fi
dbt_project_hit="$shallowest_hits"
# Strip leading "./" and the filename to get repo-root-relative dir.
DBT_ROOT="$(dirname "${dbt_project_hit#./}")"
[ "$DBT_ROOT" = "" ] && DBT_ROOT="."

# --- Airflow (requires a DAG constructor in the file; skips tests/) ---
# Use cd + relative search so the "exclude hidden" filter doesn't match
# the repo's own absolute path (common on macOS where repos live under
# ~/.worktrees or similar hidden parents).
AIRFLOW_DAGS_DIR=""
while IFS= read -r candidate; do
  [ -z "$candidate" ] && continue
  if grep -lE "\b(DAG\(|@dag\b)" "$candidate" >/dev/null 2>&1; then
    # candidate is "./path/to/dags/foo.py" — strip "./" and dirname.
    rel="${candidate#./}"
    AIRFLOW_DAGS_DIR="$(dirname "$rel")"
    break
  fi
done < <(
  find . -maxdepth 5 -path '*/dags/*.py' \
    -not -path './.*' \
    -not -path '*/dbt_packages/*' \
    -not -path '*/target/*' \
    -not -path '*/tests/*' 2>/dev/null
)

# --- Prefect ---
PREFECT_HIT=""
PREFECT_HIT="$(find . -maxdepth 4 -name 'prefect.yaml' \
  -not -path '*/dbt_packages/*' 2>/dev/null | head -1)"
if [ -z "$PREFECT_HIT" ]; then
  PREFECT_HIT="$(grep -rln "from prefect import flow\|@flow" \
    --include='*.py' . 2>/dev/null | head -1 || true)"
fi

# --- Dagster ---
DAGSTER_HIT=""
DAGSTER_HIT="$(find . -maxdepth 4 \
  \( -name 'definitions.py' -o -name 'workspace.yaml' \) \
  -not -path '*/dbt_packages/*' \
  -not -path '*/target/*' 2>/dev/null | head -1)"
if [ -z "$DAGSTER_HIT" ] && [ -f "./pyproject.toml" ]; then
  if grep -q '^\[tool.dagster\]' "./pyproject.toml" 2>/dev/null; then
    DAGSTER_HIT="./pyproject.toml"
  fi
fi

if   [ -n "$AIRFLOW_DAGS_DIR" ]; then ORCHESTRATOR="airflow"
elif [ -n "$PREFECT_HIT" ];     then ORCHESTRATOR="prefect"
elif [ -n "$DAGSTER_HIT" ];     then ORCHESTRATOR="dagster"
else                                 ORCHESTRATOR="none"
fi

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  GH_AUTH_OK="1"
else
  GH_AUTH_OK="0"
fi

# ---- All inputs validated — safe to init the run now ------------------
# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" init

# Persist. state.sh set writes `export VAR=%q` so values with spaces survive.
# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" set REPO_ROOT        "$REPO_ROOT"
source "$SCRIPT_DIR/state.sh" set SKILL_DIR        "$SKILL_DIR"
source "$SCRIPT_DIR/state.sh" set DBT_ROOT         "$DBT_ROOT"
source "$SCRIPT_DIR/state.sh" set ORCHESTRATOR     "$ORCHESTRATOR"
source "$SCRIPT_DIR/state.sh" set AIRFLOW_DAGS_DIR "$AIRFLOW_DAGS_DIR"
source "$SCRIPT_DIR/state.sh" set GH_AUTH_OK       "$GH_AUTH_OK"
source "$SCRIPT_DIR/state.sh" set PIPELINE_NAME    "$PIPELINE_NAME_RAW"

echo "Detected: dbt_root=$DBT_ROOT  orchestrator=$ORCHESTRATOR  dags_dir=${AIRFLOW_DAGS_DIR:-N/A}"
