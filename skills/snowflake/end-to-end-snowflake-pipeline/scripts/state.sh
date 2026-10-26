#!/usr/bin/env bash
# state.sh — one place to initialise, load, validate, and reset per-run
# state for the end-to-end-snowflake-pipeline skill.
#
# Design:
#   - State lives under $(git rev-parse --git-dir)/skill/pipeline/<run_id>/
#     so it is per-clone, per-run, and never committed (git-dir is
#     automatically ignored).
#   - RUN_ID is a timestamped random suffix so concurrent runs can't
#     clobber each other.
#   - Every subsequent script sources this file via `source "<...>/state.sh"
#     load <run_id>` and gets validated environment variables.
#
# Usage:
#   source scripts/state.sh init          # Phase 2: create a new run
#   source scripts/state.sh load          # all other phases: load current run
#   source scripts/state.sh set VAR VAL   # from Phase 2 while populating
#   source scripts/state.sh validate V1 V2 ...   # fail-closed check
#   source scripts/state.sh reset         # Phase 9: clean up on success

set -u

skill_state_root() {
  local git_dir
  git_dir="$(git rev-parse --git-dir 2>/dev/null)" \
    || { echo "state.sh: not inside a git repo" >&2; return 1; }
  # Normalise: git-dir may be absolute or relative.
  case "$git_dir" in
    /*) echo "$git_dir/skill/pipeline" ;;
    *)  echo "$(pwd)/$git_dir/skill/pipeline" ;;
  esac
}

skill_state_current_run_id_file() {
  echo "$(skill_state_root)/current_run"
}

skill_state_state_file() {
  local run_id="$1"
  echo "$(skill_state_root)/${run_id}/state"
}

skill_state_written_file() {
  local run_id="$1"
  echo "$(skill_state_root)/${run_id}/written"
}

cmd="${1:-}"
shift || true

case "$cmd" in
  init)
    root="$(skill_state_root)" || return 1
    mkdir -p "$root"
    RUN_ID="$(date +%Y%m%d_%H%M%S)_$$"
    export RUN_ID
    mkdir -p "$root/$RUN_ID"
    # Point `current_run` at this run so later scripts can find it.
    printf '%s\n' "$RUN_ID" > "$(skill_state_current_run_id_file)"
    # Truncate written-list — no stale entries from prior runs.
    : > "$(skill_state_written_file "$RUN_ID")"
    export STATE_FILE
    STATE_FILE="$(skill_state_state_file "$RUN_ID")"
    : > "$STATE_FILE"
    # Also expose the written-list path to callers.
    export WRITTEN_FILE
    WRITTEN_FILE="$(skill_state_written_file "$RUN_ID")"
    echo "state.sh: initialised run $RUN_ID at $STATE_FILE" >&2
    ;;

  load)
    root="$(skill_state_root)" || return 1
    current="$(skill_state_current_run_id_file)"
    [ -f "$current" ] || { echo "state.sh: no current run (did Phase 2 init?)" >&2; return 1; }
    RUN_ID="$(cat "$current")"
    export RUN_ID
    STATE_FILE="$(skill_state_state_file "$RUN_ID")"
    [ -f "$STATE_FILE" ] || { echo "state.sh: state file missing: $STATE_FILE" >&2; return 1; }
    export STATE_FILE
    export WRITTEN_FILE
    WRITTEN_FILE="$(skill_state_written_file "$RUN_ID")"
    # Load vars. State file lines are `VAR=value` with value already
    # printf %q-quoted at write time, so sourcing is safe.
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    ;;

  set)
    var="$1"
    val="$2"
    [ -n "${STATE_FILE:-}" ] || { echo "state.sh: STATE_FILE not set (call init first)" >&2; return 1; }
    # Append VAR=<printf %q value>. If VAR already exists, rewrite.
    tmp="$(mktemp)"
    grep -v "^${var}=" "$STATE_FILE" > "$tmp" 2>/dev/null || true
    # shellcheck disable=SC2059
    printf "export ${var}=%q\n" "$val" >> "$tmp"
    mv "$tmp" "$STATE_FILE"
    export "$var=$val"
    ;;

  validate)
    # `validate VAR1 VAR2 ...` — fail-closed if any is empty.
    # Use `eval` (POSIX-portable) instead of bash-only `${!v}` indirect
    # expansion, so this works in zsh (default Claude Code shell on
    # macOS) and dash too.
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
    echo "state.sh: unknown command '${cmd}'" >&2
    echo "usage: source scripts/state.sh {init|load|set VAR VAL|validate VARS...|reset}" >&2
    return 1
    ;;
esac
