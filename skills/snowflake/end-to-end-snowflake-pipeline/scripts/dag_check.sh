#!/usr/bin/env bash
# dag_check.sh — Airflow DAG parse validation. Only runs when the
# orchestrator detected in Phase 2 is Airflow; hard-stops if an Airflow
# project is detected but the DAG file is missing.

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/state.sh" load
# shellcheck disable=SC1091
source "$HERE/state.sh" validate REPO_ROOT ORCHESTRATOR PIPELINE_NAME

case "$ORCHESTRATOR" in
  airflow)
    # shellcheck disable=SC1091
    source "$HERE/state.sh" validate AIRFLOW_DAGS_DIR
    DAG_FILE="$REPO_ROOT/$AIRFLOW_DAGS_DIR/${PIPELINE_NAME}.py"
    if [ ! -f "$DAG_FILE" ]; then
      echo "dag_check.sh: DAG file missing at $DAG_FILE despite Airflow being detected" >&2
      exit 1
    fi
    python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" "$DAG_FILE" \
      && echo "DAG parse: PASS ($DAG_FILE)" \
      || { echo "DAG parse: FAIL ($DAG_FILE)" >&2; exit 1; }
    ;;
  prefect|dagster)
    echo "dag_check.sh: ORCHESTRATOR=$ORCHESTRATOR — use the native validator (prefect deployment inspect / dagster definitions validate)" >&2
    ;;
  none)
    echo "dag_check.sh: no orchestrator — skipping DAG parse" >&2
    ;;
  *)
    echo "dag_check.sh: unknown ORCHESTRATOR=$ORCHESTRATOR — refusing" >&2
    exit 1
    ;;
esac
