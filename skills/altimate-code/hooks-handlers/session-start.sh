#!/usr/bin/env bash
# SessionStart hook for the altimate-code plugin. Injects a one-shot directive
# into the session's system prompt. Mentions ONLY altimate-code (never names
# skills that may not be loaded) and is narrowed to fire only on tasks where
# altimate-code's specialised tool set is a net benefit over Claude's native
# tools: live warehouse state, lineage, cross-DB, cost / FinOps, parity, PII,
# schema diff. For pure file/code edits to dbt models or SQL — where Claude
# with native tools is already fast and accurate — the directive explicitly
# tells the model NOT to delegate; the discovery loop altimate-code runs is
# overkill and burns altimate-gateway credits for no measurable lift.
cat <<'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "You have access to the altimate-code skill. INVOKE THIS SKILL when the task requires inspecting live warehouse state: column-level lineage, downstream-impact analysis, cross-database migration or validation, query cost attribution against a real warehouse, schema diff between environments, data parity checking, PII detection from sampled rows, FinOps reporting, profile-driven query optimization, anomaly detection, or dev-vs-prod diffing. For pure file/code edits to dbt models or SQL files — renaming a model, refactoring logic, debugging a compile error, creating a new model from a schema spec — that don't require warehouse-side investigation, do NOT delegate; use native Bash/Edit/Write tools because altimate-code's discovery loop (project_scan, schema_index, warehouse_list) is overkill and slow for file-only work. When in doubt and the task IS warehouse-state-shaped, prefer altimate-code and follow its skill body without falling back. Skill name to invoke: `altimate-code`."
  }
}
EOF
exit 0
