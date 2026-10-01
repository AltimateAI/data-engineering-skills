#!/usr/bin/env bash
# Creates the pinned, docker-free Airflow environments used by eval graders
# and, separately, by the agents under test.
#
#   ${EVAL_ENV_ROOT:-~/.cache/des-evals}/airflow-3.3         grader env, apache-airflow 3.3.2, python 3.12
#   ${EVAL_ENV_ROOT:-~/.cache/des-evals}/airflow-2.11        grader env, apache-airflow 2.11.2, python 3.12
#   ${EVAL_ENV_ROOT:-~/.cache/des-evals}/agent-airflow-3.3   agent env, same packages (+ pip)
#   ${EVAL_ENV_ROOT:-~/.cache/des-evals}/agent-airflow-2.11  agent env, same packages (+ pip)
#
# Grader envs are never on an agent's PATH. Each agent env also gets
# <venv>.requirements.txt (uv pip freeze) and <venv>.manifest.json (every file's
# content hash, every symlink's target) next to it: run_eval.py compares the venv with the manifest before and
# after every attempt and restores it (uv pip sync, delete extra files, then
# uv pip sync --reinstall) when an agent changed it.
#
# Each venv gets Airflow installed with the official constraints file, plus
# duckdb and pandas (constrained where the constraints file pins them) and the
# unconstrained dev tools pytest and ruff (>=0.13, needed for stable AIR rules).
#
# Usage: evals/harness/setup_envs.sh [3.3|2.11 ...]   (default: both)
# Idempotent: re-running only installs what is missing.
set -euo pipefail

ROOT="${EVAL_ENV_ROOT:-$HOME/.cache/des-evals}"
CONSTRAINTS_BASE="https://raw.githubusercontent.com/apache/airflow"

# key -> "airflow_version python_version"
spec_for() {
  case "$1" in
    3.3) echo "3.3.2 3.12" ;;
    2.11) echo "2.11.2 3.12" ;;
    *) echo "unknown env key: $1" >&2; return 1 ;;
  esac
}

if [[ "$(uname)" == "Darwin" ]]; then
  export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
  export no_proxy='*'
fi
# Never let a caller's Airflow config leak into the smoke check below.
for v in $(env | grep -o '^AIRFLOW__[A-Z0-9_]*' || true); do unset "$v"; done

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
keys=("$@")
[[ ${#keys[@]} -eq 0 ]] && keys=(3.3 2.11)

for key in "${keys[@]}"; do
 for prefix in "" "agent-"; do
  read -r AF_VER PY_VER <<<"$(spec_for "$key")"
  VENV="$ROOT/${prefix}airflow-$key"
  CONSTRAINTS="$CONSTRAINTS_BASE/constraints-$AF_VER/constraints-$PY_VER.txt"
  echo ">> [$key] venv $VENV (python $PY_VER, apache-airflow==$AF_VER)"
  mkdir -p "$ROOT"
  if [[ -n "$prefix" ]]; then
    # Agent envs get pip, like a user's project venv, so `pip install` stays inside the venv.
    uv venv --allow-existing --seed --python "$PY_VER" "$VENV"
  else
    uv venv --allow-existing --python "$PY_VER" "$VENV"
  fi
  VIRTUAL_ENV="$VENV" uv pip install "apache-airflow==$AF_VER" duckdb pandas --constraint "$CONSTRAINTS"
  VIRTUAL_ENV="$VENV" uv pip install "ruff>=0.13" pytest
  # Smoke: import + CLI in a throwaway AIRFLOW_HOME.
  SMOKE_HOME="$(mktemp -d)"
  AIRFLOW_HOME="$SMOKE_HOME" AIRFLOW__CORE__LOAD_EXAMPLES=False PYTHONWARNINGS=ignore \
    "$VENV/bin/airflow" version
  rm -rf "$SMOKE_HOME"
  "$VENV/bin/ruff" --version
  "$VENV/bin/python" -c "import duckdb, pandas, pytest; print('duckdb', duckdb.__version__, 'pandas', pandas.__version__, 'pytest', pytest.__version__)"
  if [[ -n "$prefix" ]]; then
    find "$VENV" -name __pycache__ -type d -prune -exec rm -rf {} +
    VIRTUAL_ENV="$VENV" uv pip freeze > "$VENV.requirements.txt"
    fp=$(python3 -c "import sys; sys.path.insert(0, sys.argv[1]); import isolation; print(isolation.write_pristine(sys.argv[2]))" \
      "$HARNESS_DIR" "$VENV")
    echo ">> [$key] agent env frozen: $VENV.requirements.txt, $VENV.manifest.json (fingerprint $fp)"
  fi
 done
done
echo ">> envs ready under $ROOT"
