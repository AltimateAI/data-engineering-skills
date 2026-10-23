---
name: end-to-end-snowflake-pipeline
description: |
  Build an end-to-end Snowflake pipeline in one pass. Use when:
  (1) User says "build a pipeline for X", "create an end-to-end flow", "set up the <X> pipeline per JIRA-123"
  (2) Target warehouse is Snowflake and the project is a dbt project (or will be one)
  (3) An orchestrator (Airflow / Prefect / Dagster) is already in the repo, OR the user is OK operating without one
  (4) User expects a PR, self-review, and a ticket comment at the end
  Reads requirements (prompt or ticket), auto-detects orchestrator + VCS, builds or enhances Snowflake SQL + dbt models, adds/updates the orchestration DAG, commits on a feature branch, opens a PR, self-reviews, updates the ticket, and ends with a one-screen summary. Target wall time: <6 min.
---

# end-to-end-snowflake-pipeline

**Requirements → environment detect → build → orchestrate → PR → review → ticket → summary.**

## Prerequisites

```bash
command -v dbt           # required
command -v git           # required
command -v gh            # required if PR creation is in scope
command -v python3       # required for DAG parse validation
command -v altimate-code # optional — nicer lineage + validation
```

Must have:
- A dbt project configured for Snowflake with a working `profiles.yml`
  or env-var profile.
- `git` + `gh` authenticated against the project's remote
  (`gh auth status`) for the PR phase.
- If orchestration is in scope: the orchestrator's framework files
  already present in the repo (e.g. `dags/` for Airflow, `prefect.yaml`
  for Prefect, `dagster.yaml` for Dagster). This skill does **not**
  install Airflow / Prefect / Dagster.

If `dbt` or `git` is missing, stop and tell the user. If `gh` is
missing but everything else works, the skill still finishes but hands
off at "branch pushed" instead of opening a PR.

## Time budget

Target end-to-end runtime: **≤7 min** (420s), hard ceiling **8 min**
(480s). Per-phase caps (sum = 420s):
Phase 1 ≤30s · Phase 2 ≤30s · Phase 3 ≤10s · Phase 4 ≤90s · Phase 5 ≤75s ·
Phase 6 ≤60s · Phase 7 ≤90s · Phase 8 ≤20s · Phase 9 ≤15s.

## Workflow

### Phase 1 — Gather requirements (≤30s)

Source:
- **Inline**: use the prompt text.
- **Ticket URL** (JIRA / Linear / GitHub issue): fetch via the matching
  MCP if the tool list shows it authenticated. For GitHub issues:
  ```bash
  gh issue view <num> --json title,body,labels
  ```
  Else ask the user once to paste the body.

Extract and restate in one short block:
- Source(s) of data
- Target table(s) / grain
- Schedule / SLA
- Freshness / incremental vs full refresh

**Hard stop:** if any of these four are missing and critical, ask one
consolidated question — then proceed.

### Phase 2 — Detect the environment (≤30s) — do NOT ask the user

Run these in parallel:
```bash
find . -maxdepth 3 -name dbt_project.yml | head -1
find . -maxdepth 4 \( -path '*/dags/*.py' -o -name 'prefect.yaml' -o -name 'dagster.yaml' \) | head -5
git remote -v 2>/dev/null | head -1
command -v gh >/dev/null 2>&1 && gh auth status 2>&1 | head -3 || echo "gh: not installed"
```

Decide:
- **Orchestrator**: Airflow if `dags/` with Python DAGs exists; Prefect
  if `prefect.yaml`; Dagster if `dagster.yaml`; else none (do not add
  one — flag it).
- **VCS**: GitHub if `github.com` remote and `gh` is auth'd; else just
  commit locally and tell the user.

Print the detected stack in one line before building.

### Phase 3 — Branch (≤10s)

```bash
git checkout -b pipeline/<ticket-key-or-slug>
```

### Phase 4 — Build the Snowflake / dbt code (≤90s)

For each required layer:
- **Source**: add to `sources.yml` with `loaded_at_field` and freshness.
- **Staging**: `models/staging/stg_<src>.sql` — 1:1, renames, types.
- **Intermediate** (if logic warrants): `models/intermediate/int_<thing>.sql`.
- **Mart**: `models/marts/<domain>/<model>.sql` — materialization
  (`table` / `incremental`) chosen by expected row count and SLA.

Rules:
- Follow existing naming + folder conventions in the project.
- Incremental models: set `unique_key` and
  `on_schema_change: append_new_columns`.
- Add YAML with `description`, column `description`s, and tests
  (`not_null` + `unique` on keys, `relationships` on FKs).
- Compile locally before moving on:
  ```bash
  dbt parse && dbt compile --select +<final_model>
  ```

**Hard stop:** if `dbt parse` fails, fix before continuing — don't move
to orchestration on a broken project.

### Phase 5 — Orchestration (≤75s)

**Airflow** (most common): add or edit a DAG under `dags/`.

**Before writing a DAG, read a sibling DAG and mirror its operator
style** (Cosmos, `BashOperator`-wrapping-`dbt build`, dbt-core provider,
or dbt Cloud provider). Project convention trumps the template below.

Generic template (Airflow 2.4+ `schedule=` syntax; for older projects
use `schedule_interval=`):

```python
# dags/<pipeline>.py
from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

with DAG(
    dag_id="<pipeline>",
    start_date=datetime(2026, 10, 22),
    schedule="<cron from ticket>",
    catchup=False,
    tags=["snowflake", "dbt"],
) as dag:
    dbt_run = BashOperator(
        task_id="dbt_run_<model>",
        bash_command="cd /opt/airflow/dbt && dbt run --select +<model>",
    )
    dbt_test = BashOperator(
        task_id="dbt_test_<model>",
        bash_command="cd /opt/airflow/dbt && dbt test --select <model>",
    )
    dbt_run >> dbt_test
```

Notes on operator choice:
- If the project uses **Cosmos** (`from cosmos import DbtDag`), mirror
  that — don't swap in BashOperator.
- Do NOT import `DbtRunOperator` from `airflow.providers.dbt.cloud...`
  unless the project is actually on **dbt Cloud** — that package is dbt
  Cloud only and will ImportError on OSS dbt-core.
- The dbt-core community provider lives at `airflow-dbt` / `airflow-dbt-python`
  if the project depends on it — again, mirror what the project already uses.

**Prefect** / **Dagster**: do the equivalent in the project's style —
read a neighboring flow/asset first.

**No orchestrator detected**: skip this phase, note it in the summary,
and suggest adding one.

### Phase 6 — Validate (≤60s) — MANDATORY

```bash
dbt deps >/dev/null 2>&1 || true
dbt build --select +<final_model> --fail-fast

# DAG parses (Airflow only)
if command -v python3 >/dev/null 2>&1 && [ -f "dags/<pipeline>.py" ]; then
  python3 -c "import ast; ast.parse(open('dags/<pipeline>.py').read())" \
    && echo "DAG parse: PASS" \
    || { echo "DAG parse: FAIL"; exit 1; }
fi
```

Note on DAG parse: `ast.parse` catches syntax errors only. If the
orchestrator is reachable locally, prefer the native check
(`airflow dags list-import-errors`, `prefect deployment inspect`,
`dagster definitions check`) — the one you use should mirror the
project's CI.

If `altimate-code` is available, also:
```bash
if command -v altimate-code >/dev/null 2>&1; then
  altimate-code run "Validate the new <pipeline> DAG + dbt models: lineage from source to <final_model>, freshness configured, tests present, materializations sane. Report issues only." \
    --yolo --output /tmp/pipeline-validate.md --dir "$(pwd)"
fi
```

**Hard stop:** `dbt build` failure or DAG parse failure blocks the PR.

### Phase 7 — Commit + PR + self-review (≤90s)

Stage explicitly:
```bash
git add \
  "models/" \
  "dags/<pipeline>.py" \
  "<project_root>/sources.yml"
git commit -m "<ticket-key>: add <pipeline> end-to-end"
```

Push + PR only if `gh` is authenticated:
```bash
if gh auth status >/dev/null 2>&1; then
  git push -u origin HEAD
  gh pr create --title "<ticket-key>: <pipeline> pipeline" --body "$(cat <<'EOF'
## Summary
- <models added>
- <orchestration added/updated>
- <schedule>

## Ticket
<link>

## Validation
- dbt build --select +<final_model>: PASS
- DAG parse: PASS
- Tests added: <list>

## Lineage
<source(s)> → stg_<x> → int_<y> → <final_model>
EOF
)"
else
  echo "gh not authenticated — branch is local only; push manually to open a PR"
fi
```

Self-review (`gh pr diff` or `git diff main...HEAD`) — flag and fix:
- `SELECT *` in staging or marts
- Missing `unique_key` on incremental
- DAG with `catchup=True` not asked for
- Hardcoded dates / IDs
- Freshness missing on source

**Hard stop:** PR creation failure is not silent — report it in the
summary and tell the user the branch is still local.

### Phase 8 — Update the ticket (≤20s)

If the request came from a ticket:
- **JIRA / Linear via MCP**: post a comment linking the PR and summarizing scope.
- **GitHub issue**: `gh issue comment <num> --body "PR: <url>"`.
- **Inline (no ticket)**: skip.

Do not transition status unless the user asked.

### Phase 9 — Summary (≤15s)

Return exactly:

```
# End-to-End Snowflake Pipeline — <name>

Ticket:        <link or "inline">
Stack:         Snowflake · dbt · <orchestrator or "none detected">
Branch:        <branch>
PR:            <url or "pushed, PR not opened — gh not authenticated">

## Lineage
<source> → stg_<x> → int_<y> → <final_model>

## Code
Models:        <N> added, <N> modified
DAG:           <path>  (schedule: <cron>)  — or "skipped: no orchestrator"
Tests:         <N>

## Validation
dbt build:     PASS (<N> models, <N> tests, <seconds>s)
DAG parse:     PASS / skipped
Self-review:   <N issues fixed | clean>

## Ticket
Comment posted: YES / NO / N/A
```

## Anti-patterns (never apply)

- Install Airflow / Prefect / Dagster if none is present — flag it.
- Import `DbtRunOperator` from the dbt Cloud provider on an OSS dbt project.
- Use `catchup=True` unless the user asked for backfills.
- Introduce `SELECT *` in staging or marts.
- Modify unrelated models / DAGs.
- Merge the PR.
- Transition ticket status without being asked.

## Non-goals

- No warehouse / role / grant management on Snowflake.
- No orchestrator installation.
- No prod deploys — the PR is the handoff.

## Behavior contract

- Never claim success without a passing `dbt build` and (where applicable)
  a passing DAG parse.
- Never silently continue past a PR creation failure — surface it.
- Never ask the user about environment detection — detect from the repo.
- Never change the ticket's status unless the user asked.
