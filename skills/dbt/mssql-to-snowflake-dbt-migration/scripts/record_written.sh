#!/usr/bin/env bash
# record_written.sh — append repo-root-relative paths to the per-run
# written-files manifest. Same shape as the pipeline skill's.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" load
# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" validate REPO_ROOT DBT_ROOT WRITTEN_FILE

for p in "$@"; do
  [ -z "$p" ] && continue
  case "$p" in
    *..*)
      echo "record_written.sh: refusing path with '..': $p" >&2
      exit 1
      ;;
    "$REPO_ROOT"/*)
      rel="${p#"$REPO_ROOT"/}"
      ;;
    /*)
      echo "record_written.sh: refusing absolute path outside repo: $p" >&2
      exit 1
      ;;
    *)
      if [ "$DBT_ROOT" = "." ]; then
        rel="$p"
      else
        rel="$DBT_ROOT/$p"
      fi
      ;;
  esac
  case "$rel" in
    /*|*..*)
      echo "record_written.sh: resolved path left the repo: $rel" >&2
      exit 1
      ;;
  esac
  printf '%s\n' "$rel" >> "$WRITTEN_FILE"
done
