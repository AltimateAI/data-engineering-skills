#!/usr/bin/env bash
# record_written.sh — append a repo-root-relative path to the per-run
# written-files manifest. Called by Phase 4 / Phase 5 after each file
# write.
#
# Usage: scripts/record_written.sh <path1> [path2 ...]
#   Paths may be absolute or repo-root-relative. They are normalised
#   to repo-root-relative on write.

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/state.sh" load
# shellcheck disable=SC1091
source "$HERE/state.sh" validate REPO_ROOT WRITTEN_FILE

for p in "$@"; do
  # Normalise to repo-root-relative.
  case "$p" in
    "$REPO_ROOT"/*) rel="${p#$REPO_ROOT/}" ;;
    /*)             rel="$p" ;;   # absolute outside repo — not allowed
    *)              rel="$p" ;;   # already relative
  esac
  case "$rel" in
    /*) echo "record_written.sh: refusing path outside repo: $p" >&2; exit 1 ;;
    *..*) echo "record_written.sh: refusing path with '..': $p" >&2; exit 1 ;;
  esac
  printf '%s\n' "$rel" >> "$WRITTEN_FILE"
done
