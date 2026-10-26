#!/usr/bin/env bash
# stage.sh — Phase 7: branch + stage only the files recorded in Phase 2/5.
# macOS bash 3.2 / zsh compatible.

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/state.sh" load
# shellcheck disable=SC1091
source "$HERE/state.sh" validate REPO_ROOT DBT_ROOT TS LAYERING WRITTEN_FILE

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

# Commit message via quoted heredoc + sed injection (no shell expansion).
cat > /tmp/mssql-commit-msg.txt <<'EOF'
Migrate <scope> from MS SQL to Snowflake dbt (<layering>) — __TS__
EOF
sed -i.bak -e "s/__TS__/${TS}/" -e "s/<layering>/${LAYERING}/" /tmp/mssql-commit-msg.txt \
  && rm -f /tmp/mssql-commit-msg.txt.bak
git commit -F /tmp/mssql-commit-msg.txt

echo "Branch: $BRANCH"
