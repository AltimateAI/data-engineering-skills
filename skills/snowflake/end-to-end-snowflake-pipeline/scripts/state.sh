#!/usr/bin/env bash
# state.sh — per-run state for end-to-end-snowflake-pipeline.
#
# Design (round 10, after review feedback):
#   - Script location (where state.sh itself lives) is resolved from
#     BASH_SOURCE, so sourcing works from any cwd.
#   - State location is pinned at `init` time (from `git rev-parse
#     --git-dir` evaluated AT INIT) and stored in the state file, so
#     later `load` calls don't re-derive it from the current cwd.
#   - Concurrent runs: `init` prints the RUN_ID; callers may pass
#     SKILL_RUN_ID=... to `load`/`validate` to pick a specific run,
#     otherwise `current_run` is used. `init` refuses to overwrite
#     an existing current_run unless --force is passed.
#   - On zsh and bash 3.2 + 5.x: no `${!v}`, no `${EXTRA[@]}` without
#     the `${EXTRA[@]+...}` guard, no `mapfile`.
#
# Usage:
#   source scripts/state.sh init [--force]   # Phase 2: create a new run
#   source scripts/state.sh load             # all other phases
#   source scripts/state.sh set VAR VAL      # set/update a value
#   source scripts/state.sh validate V1 V2…  # fail-closed presence check
#   source scripts/state.sh reset            # on completion

set -u

# NOTE: callers that need this script's own location should resolve it
# from BASH_SOURCE on their side — e.g. a wrapper that sets SCRIPT_DIR
# in bash, or `(%):-%x` in zsh. This state.sh is sourced, not executed,
# so we don't need to resolve our own path here.

# State root is under the invoking git repo's git-dir, pinned at init.
# For `load`, we read `_REPO_GIT_DIR` from the state file (set at init).
_state_root_from_git_dir() {
  # Only used by `init` — load uses the pinned value.
  local git_dir
  git_dir="$(git rev-parse --git-dir 2>/dev/null)" \
    || { echo "state.sh: not inside a git repo (needed at init time)" >&2; return 1; }
  case "$git_dir" in
    /*) echo "$git_dir/skill/pipeline" ;;
    *)  echo "$(pwd)/$git_dir/skill/pipeline" ;;
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

    # Refuse to overwrite an existing current run unless --force is passed.
    if [ -f "$current_file" ] && [ "$FORCE" -eq 0 ]; then
      existing="$(cat "$current_file")"
      echo "state.sh: a run is already active ($existing); pass --force to replace or run reset first" >&2
      return 1
    fi

    RUN_ID="$(date +%Y%m%d_%H%M%S)_$$"
    mkdir -p "$root/$RUN_ID"
    printf '%s\n' "$RUN_ID" > "$current_file"

    STATE_FILE="$root/$RUN_ID/state"
    WRITTEN_FILE="$root/$RUN_ID/written"
    : > "$STATE_FILE"
    : > "$WRITTEN_FILE"

    # Pin the repo + state locations into state so later loads don't
    # re-derive from cwd. Values are printf %q quoted so names with
    # spaces survive.
    {
      printf 'export _STATE_RUN_ID=%q\n' "$RUN_ID"
      printf 'export _STATE_ROOT=%q\n'   "$root"
      printf 'export STATE_FILE=%q\n'    "$STATE_FILE"
      printf 'export WRITTEN_FILE=%q\n'  "$WRITTEN_FILE"
    } >> "$STATE_FILE"

    export RUN_ID STATE_FILE WRITTEN_FILE
    echo "state.sh: initialised run $RUN_ID at $STATE_FILE" >&2
    ;;

  load)
    # Prefer SKILL_RUN_ID override; otherwise read current_run.
    # Resolve state root the same way init did; don't trust cwd twice.
    root="$(_state_root_from_git_dir)" || return 1
    requested="${SKILL_RUN_ID:-}"
    if [ -n "$requested" ]; then
      RUN_ID="$requested"
    else
      current_file="$root/current_run"
      [ -f "$current_file" ] || { echo "state.sh: no current run (did init?)" >&2; return 1; }
      RUN_ID="$(cat "$current_file")"
    fi

    STATE_FILE="$root/$RUN_ID/state"
    [ -f "$STATE_FILE" ] || { echo "state.sh: state file missing: $STATE_FILE" >&2; return 1; }
    WRITTEN_FILE="$root/$RUN_ID/written"
    export RUN_ID STATE_FILE WRITTEN_FILE
    # Load (and export, because set lines are `export VAR=...`).
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    ;;

  set)
    var="${1:?var name required}"
    val="${2-}"
    [ -n "${STATE_FILE:-}" ] || { echo "state.sh: STATE_FILE not set (call init/load first)" >&2; return 1; }
    tmp="$(mktemp "${TMPDIR:-/tmp}/skstate.XXXXXX")"
    # Strip ANY prior line for this var (both `VAR=` and `export VAR=` forms).
    grep -v -E "^(export )?${var}=" "$STATE_FILE" > "$tmp" 2>/dev/null || true
    # shellcheck disable=SC2059
    printf "export ${var}=%q\n" "$val" >> "$tmp"
    mv "$tmp" "$STATE_FILE"
    # Also export in the current shell so the caller doesn't need to re-load.
    # shellcheck disable=SC2163
    export "$var=$val"
    ;;

  validate)
    # POSIX-portable (zsh + bash + dash). No ${!v}.
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
      # SC2115 guard: both parts non-empty, so this can never expand to `/`.
      if [ -n "$root" ] && [ -n "$run_id" ]; then
        rm -rf -- "${root:?}/${run_id:?}"
      fi
      rm -f "$current_file"
      echo "state.sh: reset run $run_id" >&2
    fi
    ;;

  *)
    echo "state.sh: usage: source scripts/state.sh {init [--force]|load|set VAR VAL|validate VARS…|reset}" >&2
    return 1
    ;;
esac
