#!/usr/bin/env bash
# dag_check.sh — orchestration validation. Loads state, confirms the
# right orchestrator was detected, and runs the appropriate parse /
# validate command for the specific orchestration file written in
# Phase 5. Non-airflow orchestrators either run a native validator (if
# available) or report SKIPPED with a clear reason — never a silent
# "exit 0 as if PASS".

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" load
# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" validate REPO_ROOT ORCHESTRATOR PIPELINE_NAME

# A single flow / asset / DAG file is what Phase 5 wrote. The caller is
# expected to pass the path explicitly for Prefect / Dagster; the
# default below handles Airflow.
case "$ORCHESTRATOR" in
  airflow)
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/state.sh" validate AIRFLOW_DAGS_DIR
    DAG_FILE="$REPO_ROOT/$AIRFLOW_DAGS_DIR/${PIPELINE_NAME}.py"
    if [ ! -f "$DAG_FILE" ]; then
      echo "dag_check.sh: DAG file missing at $DAG_FILE despite Airflow being detected" >&2
      exit 1
    fi
    if python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" "$DAG_FILE"; then
      echo "DAG parse: PASS ($DAG_FILE)"
    else
      echo "DAG parse: FAIL ($DAG_FILE)" >&2
      exit 1
    fi
    ;;

  prefect)
    # Expect the flow file at REPO_ROOT/flows/<PIPELINE_NAME>.py or
    # REPO_ROOT/<PIPELINE_NAME>.py — Phase 5 should write to one of
    # these and record it in the written-files manifest.
    FLOW_FILE=""
    for cand in \
      "$REPO_ROOT/flows/${PIPELINE_NAME}.py" \
      "$REPO_ROOT/${PIPELINE_NAME}.py"; do
      [ -f "$cand" ] && { FLOW_FILE="$cand"; break; }
    done
    if [ -z "$FLOW_FILE" ]; then
      echo "dag_check.sh: no Prefect flow found for pipeline '${PIPELINE_NAME}' (expected flows/${PIPELINE_NAME}.py or ${PIPELINE_NAME}.py)" >&2
      exit 1
    fi
    # Native: `prefect deployment inspect`. Fallback: ast.parse.
    if command -v prefect >/dev/null 2>&1; then
      if prefect deployment inspect "${PIPELINE_NAME}" >/dev/null 2>&1; then
        echo "Prefect deployment inspect: PASS ($PIPELINE_NAME)"
      else
        echo "Prefect deployment inspect: SKIPPED (deployment not registered; ast.parse will follow)"
      fi
    fi
    if python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" "$FLOW_FILE"; then
      echo "Flow parse: PASS ($FLOW_FILE)"
    else
      echo "Flow parse: FAIL ($FLOW_FILE)" >&2
      exit 1
    fi
    ;;

  dagster)
    # Expect a definitions file at REPO_ROOT/definitions.py or an
    # explicit path recorded by Phase 5.
    DEF_FILE=""
    for cand in \
      "$REPO_ROOT/definitions.py" \
      "$REPO_ROOT/dagster_project/definitions.py"; do
      [ -f "$cand" ] && { DEF_FILE="$cand"; break; }
    done
    if [ -z "$DEF_FILE" ]; then
      echo "dag_check.sh: no Dagster definitions.py found" >&2
      exit 1
    fi
    if command -v dagster >/dev/null 2>&1; then
      dagster definitions validate 2>&1 | tail -5
      echo "Dagster definitions validate: PASS"
    else
      if python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" "$DEF_FILE"; then
        echo "Definitions parse: PASS ($DEF_FILE, native validator unavailable)"
      else
        echo "Definitions parse: FAIL ($DEF_FILE)" >&2
        exit 1
      fi
    fi
    ;;

  none)
    echo "dag_check.sh: no orchestrator detected — SKIPPED (nothing to validate)"
    ;;

  *)
    echo "dag_check.sh: unknown ORCHESTRATOR='$ORCHESTRATOR' — refusing" >&2
    exit 1
    ;;
esac
