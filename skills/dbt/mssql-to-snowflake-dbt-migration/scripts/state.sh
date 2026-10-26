#!/usr/bin/env bash
# state.sh — per-run state for mssql-to-snowflake-dbt-migration.
# Same shape as the pipeline skill's state.sh; see that for design notes.

set -u

skill_state_root() {
  local git_dir
  git_dir="$(git rev-parse --git-dir 2>/dev/null)" \
    || { echo "state.sh: not inside a git repo" >&2; return 1; }
  case "$git_dir" in
    /*) echo "$git_dir/skill/mssql_migration" ;;
    *)  echo "$(pwd)/$git_dir/skill/mssql_migration" ;;
  esac
}
skill_state_current_run_id_file() { echo "$(skill_state_root)/current_run"; }
skill_state_state_file()          { echo "$(skill_state_root)/$1/state"; }
skill_state_written_file()        { echo "$(skill_state_root)/$1/written"; }

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
    WRITTEN_FILE="$(skill_state_written_file "$RUN_ID")"; : > "$WRITTEN_FILE"
    export STATE_FILE WRITTEN_FILE
    echo "state.sh: initialised run $RUN_ID" >&2
    ;;
  load)
    root="$(skill_state_root)" || return 1
    current="$(skill_state_current_run_id_file)"
    [ -f "$current" ] || { echo "state.sh: no current run (did Phase 4 init?)" >&2; return 1; }
    RUN_ID="$(cat "$current")"; export RUN_ID
    STATE_FILE="$(skill_state_state_file "$RUN_ID")"
    [ -f "$STATE_FILE" ] || { echo "state.sh: state file missing: $STATE_FILE" >&2; return 1; }
    WRITTEN_FILE="$(skill_state_written_file "$RUN_ID")"
    export STATE_FILE WRITTEN_FILE
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    ;;
  set)
    var="$1"; val="$2"
    [ -n "${STATE_FILE:-}" ] || { echo "state.sh: STATE_FILE not set (call init first)" >&2; return 1; }
    tmp="$(mktemp)"
    # Match both `VAR=...` and `export VAR=...` so re-setting strips the
    # old line regardless of which form it was written in.
    grep -v -E "^(export )?${var}=" "$STATE_FILE" > "$tmp" 2>/dev/null || true
    # shellcheck disable=SC2059
    printf "export ${var}=%q\n" "$val" >> "$tmp"
    mv "$tmp" "$STATE_FILE"
    export "$var=$val"
    ;;
  validate)
    # Use `eval` (POSIX-portable), not bash-only `${!v}` indirect
    # expansion — zsh and dash reject the latter.
    for v in "$@"; do
      eval "val=\${$v:-}"
      if [ -z "$val" ]; then
        echo "state.sh: required variable \$$v is empty or unset" >&2
        return 1
      fi
    done
    unset val
    ;;
  reset)
    root="$(skill_state_root)" || return 1
    current="$(skill_state_current_run_id_file)"
    if [ -f "$current" ]; then
      run_id="$(cat "$current")"
      rm -rf "$root/$run_id"
      rm -f "$current"
      echo "state.sh: reset run $run_id" >&2
    fi
    ;;
  *)
    echo "state.sh: usage: source scripts/state.sh {init|load|set VAR VAL|validate VARS...|reset}" >&2
    return 1
    ;;
esac
