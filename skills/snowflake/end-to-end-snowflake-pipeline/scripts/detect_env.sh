#!/usr/bin/env bash
# detect_env.sh — Phase 2 environment detection.
#
# Populates (via state.sh set):
#   REPO_ROOT, DBT_ROOT, ORCHESTRATOR, AIRFLOW_DAGS_DIR, GH_AUTH_OK,
#   PIPELINE_NAME (validated).
#
# Usage: scripts/detect_env.sh <pipeline_name>

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/state.sh" init

PIPELINE_NAME_RAW="${1:-}"
if [ -z "$PIPELINE_NAME_RAW" ]; then
  echo "detect_env.sh: pipeline name required (arg 1)" >&2
  exit 1
fi

# Validate: lowercase ascii, digits, underscore, length 1..64.
# Rejects shell metacharacters, path traversal, Jinja etc.
if ! [[ "$PIPELINE_NAME_RAW" =~ ^[a-z][a-z0-9_]{0,63}$ ]]; then
  echo "detect_env.sh: invalid pipeline name '$PIPELINE_NAME_RAW'" >&2
  echo "  must match ^[a-z][a-z0-9_]{0,63}\$" >&2
  exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"

# --- dbt project (shallowest, excluding dbt_packages/ and target/) ---
dbt_project_candidates="$(find "$REPO_ROOT" -maxdepth 4 -name dbt_project.yml \
  -not -path '*/dbt_packages/*' \
  -not -path '*/target/*' 2>/dev/null \
  | awk -F/ '{print NF" "$0}' | sort -n)"
shallowest_depth="$(echo "$dbt_project_candidates" | head -1 | awk '{print $1}')"
shallowest_hits="$(echo "$dbt_project_candidates" | awk -v d="$shallowest_depth" '$1==d {print $2}')"
shallowest_count="$(echo "$shallowest_hits" | grep -c . || true)"

if [ -z "$shallowest_hits" ]; then
  echo "detect_env.sh: no dbt_project.yml found" >&2
  exit 1
fi
if [ "$shallowest_count" -gt 1 ]; then
  echo "detect_env.sh: multiple dbt_project.yml at shallowest depth:" >&2
  echo "$shallowest_hits" >&2
  exit 1
fi
dbt_project_hit="$shallowest_hits"
DBT_ROOT="$(dirname "${dbt_project_hit#$REPO_ROOT/}")"
[ "$DBT_ROOT" = "" ] && DBT_ROOT="."

# --- Airflow (requires a DAG constructor in the file; skips tests/) ---
AIRFLOW_DAGS_DIR=""
while IFS= read -r candidate; do
  grep -lE "\b(DAG\(|@dag\b)" "$candidate" >/dev/null 2>&1 && {
    AIRFLOW_DAGS_DIR="$(dirname "${candidate#$REPO_ROOT/}")"
    break
  }
done < <(find "$REPO_ROOT" -maxdepth 5 -path '*/dags/*.py' \
         -not -path '*/.*' \
         -not -path '*/dbt_packages/*' \
         -not -path '*/target/*' \
         -not -path '*/tests/*' 2>/dev/null)

# --- Prefect ---
PREFECT_HIT=""
PREFECT_HIT="$(find "$REPO_ROOT" -maxdepth 4 -name 'prefect.yaml' \
               -not -path '*/dbt_packages/*' 2>/dev/null | head -1)"
if [ -z "$PREFECT_HIT" ]; then
  PREFECT_HIT="$(grep -rln "from prefect import flow\|@flow" \
                 --include='*.py' "$REPO_ROOT" 2>/dev/null | head -1 || true)"
fi

# --- Dagster ---
DAGSTER_HIT=""
DAGSTER_HIT="$(find "$REPO_ROOT" -maxdepth 4 \
               \( -name 'definitions.py' -o -name 'workspace.yaml' \) \
               -not -path '*/dbt_packages/*' \
               -not -path '*/target/*' 2>/dev/null | head -1)"
if [ -z "$DAGSTER_HIT" ] && [ -f "$REPO_ROOT/pyproject.toml" ]; then
  if grep -q '^\[tool.dagster\]' "$REPO_ROOT/pyproject.toml" 2>/dev/null; then
    DAGSTER_HIT="$REPO_ROOT/pyproject.toml"
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

# Persist. state.sh set uses printf %q, so unsafe chars are quoted.
source "$HERE/state.sh" set REPO_ROOT "$REPO_ROOT"
source "$HERE/state.sh" set DBT_ROOT "$DBT_ROOT"
source "$HERE/state.sh" set ORCHESTRATOR "$ORCHESTRATOR"
source "$HERE/state.sh" set AIRFLOW_DAGS_DIR "$AIRFLOW_DAGS_DIR"
source "$HERE/state.sh" set GH_AUTH_OK "$GH_AUTH_OK"
source "$HERE/state.sh" set PIPELINE_NAME "$PIPELINE_NAME_RAW"

echo "Detected: dbt_root=$DBT_ROOT  orchestrator=$ORCHESTRATOR  dags_dir=${AIRFLOW_DAGS_DIR:-N/A}"
