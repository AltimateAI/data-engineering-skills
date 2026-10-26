#!/usr/bin/env bash
# record_written.sh — same shape as the pipeline skill's; records a
# repo-root-relative path to this run's written-files list.

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/state.sh" load
# shellcheck disable=SC1091
source "$HERE/state.sh" validate REPO_ROOT WRITTEN_FILE

for p in "$@"; do
  case "$p" in
    "$REPO_ROOT"/*) rel="${p#$REPO_ROOT/}" ;;
    /*)             rel="$p" ;;
    *)              rel="$p" ;;
  esac
  case "$rel" in
    /*)   echo "record_written.sh: refusing path outside repo: $p" >&2; exit 1 ;;
    *..*) echo "record_written.sh: refusing path with '..': $p" >&2; exit 1 ;;
  esac
  printf '%s\n' "$rel" >> "$WRITTEN_FILE"
done
