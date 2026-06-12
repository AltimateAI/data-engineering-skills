#!/usr/bin/env bash
# SessionStart hook for the altimate-code skill. Injects a one-shot directive
# into the session's system prompt telling the agent to consult Skills before
# reading files when the task is data-engineering shaped.
cat <<'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "You have access to data-engineering skills via plugins: dbt-skills (refactoring, creating, testing, debugging, documenting, migrating dbt models, incremental models), snowflake-skills (finding expensive queries, optimizing query by id, optimizing query text), and altimate-code (warehouse access, column-level lineage, dbt builds against real warehouses, cross-database operations, multi-warehouse data parity). When the user's task involves dbt models, SQL refactoring, data warehouse work, query optimization, or cross-database operations, INVOKE THE Skill TOOL FIRST — before reading files, writing code, or starting work directly. Prefer altimate-code:altimate-code when the task needs live warehouse access, column-level lineage, dbt builds against a real warehouse, profiling, cost attribution, or cross-database migration. Use Skill consultation as your first action on every data-engineering task; the skill's body will tell you how to proceed."
  }
}
EOF
exit 0
