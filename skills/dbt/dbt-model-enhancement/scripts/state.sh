#!/usr/bin/env bash
# state.sh — per-run state for dbt-model-enhancement.
# Shape identical to the pipeline skill's state.sh; see that for notes.

set -u

_state_root_from_git_dir() {
  local git_dir
  git_dir="$(git rev-parse --git-dir 2>/dev/null)" \
    || { echo "state.sh: not inside a git repo (needed at init time)" >&2; return 1; }
  case "$git_dir" in
    /*) echo "$git_dir/skill/dme" ;;
    *)  echo "$(pwd)/$git_dir/skill/dme" ;;
  esac
}

cmd="${1:-}"
shift || true

case "$cmd" in
  init)
    FORCE=0
    [ "${1:-}" = "--force" ] && FORCE=1
    root="$(_state_root_from_git_dir)" || return 1
    mkdir -p "$root"
    current_file="$root/current_run"
    if [ -f "$current_file" ] && [ "$FORCE" -eq 0 ]; then
      existing="$(cat "$current_file")"
      echo "state.sh: a run is already active ($existing); pass --force to replace or run reset first" >&2
      return 1
    fi
    RUN_ID="$(date +%Y%m%d_%H%M%S)_$$"
    mkdir -p "$root/$RUN_ID"
    printf '%s\n' "$RUN_ID" > "$current_file"
    STATE_FILE="$root/$RUN_ID/state"
    : > "$STATE_FILE"
    {
      printf 'export _STATE_RUN_ID=%q\n' "$RUN_ID"
      printf 'export _STATE_ROOT=%q\n'   "$root"
      printf 'export STATE_FILE=%q\n'    "$STATE_FILE"
    } >> "$STATE_FILE"
    export RUN_ID STATE_FILE
    echo "state.sh: initialised run $RUN_ID at $STATE_FILE" >&2
    ;;

  load)
    root="$(_state_root_from_git_dir)" || return 1
    requested="${SKILL_RUN_ID:-}"
    if [ -n "$requested" ]; then
      RUN_ID="$requested"
    else
      current_file="$root/current_run"
      [ -f "$current_file" ] || { echo "state.sh: no current run" >&2; return 1; }
      RUN_ID="$(cat "$current_file")"
    fi
    STATE_FILE="$root/$RUN_ID/state"
    [ -f "$STATE_FILE" ] || { echo "state.sh: state file missing: $STATE_FILE" >&2; return 1; }
    export RUN_ID STATE_FILE
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    ;;

  set)
    var="${1:?var name required}"
    val="${2-}"
    [ -n "${STATE_FILE:-}" ] || { echo "state.sh: STATE_FILE not set" >&2; return 1; }
    tmp="$(mktemp "${TMPDIR:-/tmp}/skstate.XXXXXX")"
    grep -v -E "^(export )?${var}=" "$STATE_FILE" > "$tmp" 2>/dev/null || true
    # shellcheck disable=SC2059
    printf "export ${var}=%q\n" "$val" >> "$tmp"
    mv "$tmp" "$STATE_FILE"
    # shellcheck disable=SC2163
    export "$var=$val"
    ;;

  validate)
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
    root="$(_state_root_from_git_dir)" || return 1
    current_file="$root/current_run"
    if [ -f "$current_file" ]; then
      run_id="$(cat "$current_file")"
      if [ -n "$root" ] && [ -n "$run_id" ]; then
        rm -rf -- "${root:?}/${run_id:?}"
      fi
      rm -f "$current_file"
    fi
    ;;

  *)
    echo "state.sh: usage" >&2
    return 1
    ;;
esac
