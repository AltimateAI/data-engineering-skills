---
name: dbt-model-enhancement
description: |
  Enhance an existing dbt model to meet a ticket or inline instruction. Use when:
  (1) User says "update <model> per JIRA-123", "add column X to this model", "enhance <model> based on this ticket"
  (2) Task provides a ticket URL (JIRA, Linear, GitHub issue) plus a target dbt model
  (3) Task is a scoped change to a specific existing model — not a new model and not a cross-model refactor
  (4) User expects a PR + self-review at the end
  Finds the model, applies the change, runs dbt build on the model + downstream, opens a PR, self-reviews, and summarizes. Target wall time: <6 min. Does not create models from scratch (use `creating-dbt-models`) or restructure them (use `refactoring-dbt-models`).
---

# dbt-model-enhancement

**Locate model → read ticket → change → validate → PR → review → summary.**

## Prerequisites

Verify what's available before invoking — do not assume.

```bash
command -v dbt   # required
command -v gh    # required if PR creation is in scope
command -v git   # required
command -v altimate-code   # optional — nicer parity + diff
```

Must have:
- A working dbt project (`dbt_project.yml` at the project root) with
  warehouse credentials configured in `profiles.yml` or env vars.
- `git` + `gh` authenticated against the project's remote
  (`gh auth status`) if PR creation is expected.

Nice to have:
- A JIRA/Linear/Atlassian MCP for ticket fetching. If not available,
  the skill falls back to GitHub issues via `gh` or asks the user to
  paste the ticket body.

If `dbt` or `git` is missing, stop and tell the user.

## Time budget

Target end-to-end runtime: **≤6 min** (360s), hard ceiling **8 min**
(480s). Per-phase caps (sum = 360s):
Phase 1 ≤20s · Phase 2 ≤30s · Phase 3 ≤10s · Phase 4 ≤90s · Phase 5 ≤90s ·
Phase 6 ≤90s · Phase 7 ≤30s.

## Inputs

- **Model**: name, file path, or "the <model> model" (resolve via `find models -name "<name>.sql"`).
- **Change source**: a JIRA / Linear / GitHub issue URL, OR inline instructions in the prompt.
- Default base branch: `main` (confirm from `git symbolic-ref refs/remotes/origin/HEAD` if unsure).

## Workflow

### Phase 1 — Locate the model (≤20s)

```bash
find models -type f -name "<model>.sql" | head
```

If multiple matches, pick the one whose directory best matches the
ticket context (e.g. `marts/finance/` for a revenue ticket) and
confirm the choice in one sentence before editing.

Read the model file and its YAML sibling (`<model>.yml` or the shared
`_models.yml` in the same folder).

**Hard stop:** if the model doesn't exist, do not create one — redirect
to `creating-dbt-models` and stop.

### Phase 2 — Read the ticket (≤30s)

Resolve the change source in this order (use whichever is available):

1. **JIRA URL** (`*.atlassian.net/browse/<KEY>`): use the Atlassian MCP
   if the tool list shows it authenticated. Else fall through.
2. **GitHub issue**:
   ```bash
   gh issue view <num> --json title,body,labels
   ```
3. **Linear**: if a Linear MCP is listed, use it; else fall through.
4. **Fallback**: ask the user once to paste the ticket body.
5. **Inline**: use the prompt text directly.

Extract: (1) new/changed columns, (2) new filter or grain, (3) tests
required, (4) acceptance criteria.

**Hard stop:** if any of these four are both missing AND critical to
the change, ask one consolidated clarifying question — do not guess.

### Phase 3 — Branch (≤10s)

```bash
git checkout -b enhance/<ticket-key-or-slug>
```

Use the ticket key if available (e.g. `enhance/DATA-412`), otherwise a
short slug derived from the instruction.

### Phase 4 — Apply the change (≤90s)

Edit `<model>.sql` and its YAML. Rules:

- Preserve existing CTE structure and naming conventions in that folder.
- New columns go at the **end** of the final SELECT unless the ticket
  specifies ordering.
- Add tests for every new column (`not_null` + domain-appropriate —
  `unique`, `accepted_values`, `relationships`) in the YAML.
- Update the model `description` in YAML if the grain or purpose changed.
- Do not touch unrelated models.

**Hard stop:** if the change would alter the model's grain in a way the
ticket didn't ask for, stop and surface it.

### Phase 5 — Validate (≤90s) — MANDATORY

```bash
dbt deps >/dev/null 2>&1 || true
dbt parse
dbt build --select <model>+ --fail-fast
```

`<model>+` builds the model and its downstream — catches broken refs.
If a slim CI selector is set up (`state:modified+`), use it instead.

If `altimate-code` is available, also run a schema + sample diff:
```bash
if command -v altimate-code >/dev/null 2>&1; then
  altimate-code run "Compare <model> on this branch vs main: row count delta, column schema diff, and top 20 example rows that differ. Keep it under 300 words." \
    --yolo --output /tmp/model-diff.md --dir "$(pwd)"
fi
```

**Hard stop:** if `dbt build` fails, fix and re-run before proceeding.
If it fails three times, stop and reassess — do not keep retrying.

### Phase 6 — PR + self-review (≤90s)

Stage explicitly — do not use `git add -A`:
```bash
git add \
  "models/.../<model>.sql" \
  "models/.../<model>.yml"      # or the shared _models.yml you edited
git commit -m "<ticket-key>: <one-line summary>"
git push -u origin HEAD
```

If `gh` is authenticated:
```bash
gh pr create --title "<ticket-key>: <summary>" --body "$(cat <<'EOF'
## Summary
<2-3 bullets of what changed>

## Ticket
<link>

## Validation
- dbt build --select <model>+ : PASS
- New tests: <list>
- Downstream models rebuilt: <count>

## Parity
<row count delta, schema diff — from altimate-code output if available>
EOF
)"
```

If `gh` is not authenticated, skip PR creation and tell the user the
branch is pushed and ready for them to open the PR manually.

Self-review: `gh pr diff` (or `git diff main...HEAD`) and look specifically for:
- Any `SELECT *` introduced
- Hardcoded dates / IDs
- Tests missing for new columns
- YAML description out of date

Post review comments inline only if you find real issues — do not comment "LGTM".

### Phase 7 — Summary (≤30s)

Return to the user:

```
# dbt Model Enhancement — <model>

Ticket:     <link>
Branch:     <branch>
PR:         <url or "pushed, PR not opened — gh not authenticated">

Changes:
- <bullet>
- <bullet>

Validation:
- dbt build: PASS (<N> models, <N> tests)
- Row count: <before> → <after>
- Schema:    <added cols> / <changed cols>

Self-review: <N issues found and fixed before pushing | clean>
```

## Anti-patterns (never apply)

- Introduce `SELECT *` in a staging or mart model.
- Hardcode dates, IDs, or environment-specific values.
- Rename an existing column without updating downstream refs
  (`grep -r "ref('<model>')" models/` first).
- Change the grain of the model without the ticket asking for it.
- Merge the PR. Hand off at review-ready.
- Modify models the ticket did not scope to.

## Non-goals

- No model creation — defer to `creating-dbt-models`.
- No refactoring beyond what the ticket requires — defer to `refactoring-dbt-models`.
- No warehouse-level changes (grants, warehouses, roles).

## Behavior contract

- Never claim success without a passing `dbt build --select <model>+`.
- Never open a PR without a self-review pass.
- Never rename / drop existing columns without a documented downstream
  check.
