#!/usr/bin/env bash
# state.sh — per-run state for dbt-model-enhancement.
# Same shape as the pipeline / mssql scripts; see those for notes.

set -u

skill_state_root() {
  local git_dir
  git_dir="$(git rev-parse --git-dir 2>/dev/null)" \
    || { echo "state.sh: not inside a git repo" >&2; return 1; }
  case "$git_dir" in
    /*) echo "$git_dir/skill/dme" ;;
    *)  echo "$(pwd)/$git_dir/skill/dme" ;;
  esac
}
skill_state_current_run_id_file() { echo "$(skill_state_root)/current_run"; }
skill_state_state_file()          { echo "$(skill_state_root)/$1/state"; }

cmd="${1:-}"; shift || true

case "$cmd" in
  init)
    root="$(skill_state_root)" || return 1
    mkdir -p "$root"
    RUN_ID="$(date +%Y%m%d_%H%M%S)_$$"
    export RUN_ID
    mkdir -p "$root/$RUN_ID"
    printf '%s\n' "$RUN_ID" > "$(skill_state_current_run_id_file)"
    STATE_FILE="$(skill_state_state_file "$RUN_ID")"; : > "$STATE_FILE"
    export STATE_FILE
    echo "state.sh: initialised run $RUN_ID" >&2
    ;;
  load)
    root="$(skill_state_root)" || return 1
    current="$(skill_state_current_run_id_file)"
    [ -f "$current" ] || { echo "state.sh: no current run" >&2; return 1; }
    RUN_ID="$(cat "$current")"; export RUN_ID
    STATE_FILE="$(skill_state_state_file "$RUN_ID")"
    [ -f "$STATE_FILE" ] || { echo "state.sh: state file missing: $STATE_FILE" >&2; return 1; }
    export STATE_FILE
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    ;;
  set)
    var="$1"; val="$2"
    [ -n "${STATE_FILE:-}" ] || { echo "state.sh: STATE_FILE not set" >&2; return 1; }
    tmp="$(mktemp)"
    grep -v "^${var}=" "$STATE_FILE" > "$tmp" 2>/dev/null || true
    # shellcheck disable=SC2059
    printf "${var}=%q\n" "$val" >> "$tmp"
    mv "$tmp" "$STATE_FILE"
    export "$var=$val"
    ;;
  validate)
    for v in "$@"; do
      if [ -z "${!v:-}" ]; then
        echo "state.sh: required variable \$$v is empty or unset" >&2
        return 1
      fi
    done
    ;;
  reset)
    root="$(skill_state_root)" || return 1
    current="$(skill_state_current_run_id_file)"
    if [ -f "$current" ]; then
      run_id="$(cat "$current")"
      rm -rf "$root/$run_id"
      rm -f "$current"
    fi
    ;;
  *)
    echo "state.sh: usage" >&2
    return 1
    ;;
esac
