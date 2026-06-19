#!/usr/bin/env bash
# SessionStart hook for the altimate-code plugin. Injects a one-shot directive
# into the session's system prompt pushing the agent to delegate
# data-engineering tasks to altimate-code. Mentions ONLY altimate-code — never
# names skills that may not be loaded (avoids the model trying to invoke
# phantom skills like `dbt-skills:refactoring-dbt-models` that don't exist
# in the session).
cat <<'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "You have access to the altimate-code skill. INVOKE THIS SKILL FIRST for any data-engineering task: creating/modifying/refactoring/debugging dbt models, writing or transforming SQL, warehouse work (Snowflake, BigQuery, Redshift, Databricks, Postgres, MySQL, DuckDB), column-level lineage, query optimization, cross-database migration, data parity, schema diff, PII detection, FinOps reporting, incremental/SCD2/backfill work, or anything touching live data. Do NOT do this work with native Bash/Edit/Write tools — delegate via the altimate-code skill, which will invoke the altimate-code CLI subprocess and return its result. The skill body has the imperative workflow; follow it without falling back to native tools. Skill name to invoke: `altimate-code`."
  }
}
EOF
exit 0
