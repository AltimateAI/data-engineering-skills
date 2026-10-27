#!/usr/bin/env bash
# stage.sh — Phase 7: branch + stage only the files recorded in Phase 2/5.
# macOS bash 3.2 / zsh compatible.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" load
# shellcheck disable=SC1091
source "$SCRIPT_DIR/state.sh" validate REPO_ROOT DBT_ROOT TS LAYERING SCOPE_SELECTOR WRITTEN_FILE _STATE_ROOT _STATE_RUN_ID

cd "$REPO_ROOT"

BRANCH="migration/mssql-to-snowflake-${TS}"
git checkout -b "$BRANCH"   # fails if exists; set -e stops the script

[ -s "$WRITTEN_FILE" ] || { echo "stage.sh: no files recorded in $WRITTEN_FILE" >&2; exit 1; }

while IFS= read -r p; do
  [ -z "$p" ] && continue
  if [ -f "$REPO_ROOT/$p" ]; then
    git add -- "$REPO_ROOT/$p"
  else
    echo "stage.sh: recorded path missing on disk: $p" >&2
    exit 1
  fi
done < <(awk '!seen[$0]++' "$WRITTEN_FILE")

# dbt_project.yml only if actually modified.
if [ -n "$(git status --porcelain "$DBT_ROOT/dbt_project.yml" 2>/dev/null)" ]; then
  git add "$DBT_ROOT/dbt_project.yml"
fi

# Method 2's generate_schema_name macro, only if NEW and untracked.
if [ -f "$DBT_ROOT/macros/get_custom_schema.sql" ] \
   && git status --porcelain "$DBT_ROOT/macros/get_custom_schema.sql" 2>/dev/null | grep -q '^??'; then
  git add "$DBT_ROOT/macros/get_custom_schema.sql"
fi

# Commit message in the run's state dir (not a fixed /tmp path shared
# across runs/users). Substitute SCOPE_SELECTOR + LAYERING + TS from
# state — populated via `printf %q`, so no shell metacharacter leak.
MSG_FILE="$_STATE_ROOT/$_STATE_RUN_ID/commit_msg.txt"
cat > "$MSG_FILE" <<EOF
Migrate ${SCOPE_SELECTOR} from MS SQL to Snowflake dbt (${LAYERING}) — ${TS}
EOF
git commit -F "$MSG_FILE"

echo "Branch: $BRANCH"
