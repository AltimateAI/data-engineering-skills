#!/usr/bin/env bash
# stage.sh — self-review + stage only the files Phase 4/5 recorded as
# written. macOS bash 3.2 + zsh compatible (no mapfile, no namerefs).
#
# Usage:
#   scripts/stage.sh review   # Phase 7: mark intent-to-add + show diff
#   scripts/stage.sh commit   # Phase 8: git add only recorded paths

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/state.sh" load
# shellcheck disable=SC1091
source "$HERE/state.sh" validate REPO_ROOT DBT_ROOT WRITTEN_FILE

cmd="${1:-}"
cd "$REPO_ROOT"

[ -s "$WRITTEN_FILE" ] || { echo "stage.sh: no files recorded in $WRITTEN_FILE — did Phase 4/5 run?" >&2; exit 1; }

existing_recorded=()
missing_recorded=()
# bash 3.2 / zsh portable loop.
while IFS= read -r p; do
  [ -z "$p" ] && continue
  if [ -f "$REPO_ROOT/$p" ]; then
    existing_recorded+=("$REPO_ROOT/$p")
  else
    missing_recorded+=("$REPO_ROOT/$p")
  fi
done < <(awk '!seen[$0]++' "$WRITTEN_FILE")

if [ "${#missing_recorded[@]}" -gt 0 ]; then
  echo "stage.sh: recorded paths missing on disk:" >&2
  printf '  %s\n' "${missing_recorded[@]}" >&2
  echo "stage.sh: run was likely from a different branch or Phase 4/5 didn't finish — aborting" >&2
  exit 1
fi

case "$cmd" in
  review)
    git add --intent-to-add -- "${existing_recorded[@]}"
    git diff -- "${existing_recorded[@]}"
    git status --porcelain -- "${existing_recorded[@]}"
    ;;

  commit)
    git add -- "${existing_recorded[@]}"
    # dbt_project.yml only if actually modified — explicit if/then/fi
    # (NOT cond && cmd, which trips `set -e` when there's no change).
    if [ -n "$(git status --porcelain "$DBT_ROOT/dbt_project.yml" 2>/dev/null)" ]; then
      git add "$DBT_ROOT/dbt_project.yml"
    fi
    ;;

  *)
    echo "stage.sh: usage: scripts/stage.sh {review|commit}" >&2
    exit 1
    ;;
esac
