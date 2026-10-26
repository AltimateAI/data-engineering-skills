#!/usr/bin/env bash
# record_written.sh — append repo-root-relative paths to the per-run
# written-files manifest.
#
# Path resolution:
#   - Absolute paths must be inside the repo; stored repo-relative.
#   - Relative paths are resolved against $REPO_ROOT/$DBT_ROOT (the
#     dbt project root), NOT the shell's cwd — callers typically pass
#     dbt-project-relative paths like `models/staging/stg_x.sql`.
#   - Paths containing `..` are refused.

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
      # Relative — resolve against DBT_ROOT (callers pass
      # dbt-project-relative paths such as 'models/staging/stg_x.sql').
      # If DBT_ROOT == ".", that's the repo root; otherwise the dbt
      # project subdir.
      if [ "$DBT_ROOT" = "." ]; then
        rel="$p"
      else
        rel="$DBT_ROOT/$p"
      fi
      ;;
  esac
  # Final sanity: the recorded path must exist in the repo. We don't
  # require that it exist YET (Phase 5 may append paths before writing
  # the file), but we insist it's clean and inside the repo tree.
  case "$rel" in
    /*|*..*)
      echo "record_written.sh: resolved path left the repo: $rel" >&2
      exit 1
      ;;
  esac
  printf '%s\n' "$rel" >> "$WRITTEN_FILE"
done
