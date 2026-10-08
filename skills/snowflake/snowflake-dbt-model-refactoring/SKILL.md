---
name: snowflake-dbt-model-refactoring
description: >
  Refactor a bloated dbt model on Snowflake safely and produce a quantified
  before/after report that explains **which qualities improved and why** —
  not just raw deltas. Extends the standard refactor flow with (1) downstream
  impact analysis via `dbt-analyze`, (2) row-count + column-hash parity
  validation via `data-parity`, (3) a report that lands a Bottleneck Summary
  and an "Outcome axes improved" table (readability, maintainability,
  performance, cost, governance, best-practices), and (4) an optional
  post-refactor warehouse benchmark against real Snowflake query history
  offered at the end. Use when the user says "refactor this model", "clean
  up this model", or points at a model that is oversized / over-joined /
  duplicated across the project — and the warehouse is Snowflake. Delegates
  to Altimate skills — does not reinvent them.
---

# snowflake-dbt-model-refactoring

## When to invoke

Trigger this skill when any of the following is true for a target dbt model
**on a Snowflake-backed dbt project**:

- More than ~200 lines
- More than 5 joins in a single query block
- A CTE longer than ~50 lines
- Logic duplicated across 3+ models (payment pivots, RFM buckets, etc.)
- Hardcoded lists / thresholds repeated inline
- Downstream consumers exist and would be affected by structural changes

If the project targets BigQuery, Redshift, or Databricks, use the generic
`refactoring-dbt-models` skill instead — Phase 7's warehouse benchmark is
Snowflake-specific.

## Non-goals

- Do **not** rewrite for performance alone — that is the job of `query-optimize`
- Do **not** change model outputs — refactoring must preserve row count and per-row values
- Do **not** touch models the user did not point at, even if they look messy

## Time budget

Target end-to-end runtime: **5–6 minutes**, hard ceiling **8 minutes**.
The individual phases below have explicit budgets:
Phase 1 ≤90s · Phase 2 ≤60s · Phase 3 ≤90s · Phase 4 ≤90s · Phase 5 ≤30s ·
Phase 6 ≤60s. If a phase exceeds its budget, stop the extra work and move
on — the report is the deliverable, not a comprehensive audit.

## Inputs to collect from the user (ask once, up front)

Ask **only** these two questions before proceeding. Do NOT ask about
warehouse benchmarking here — that comes at the end (see Phase 7).

1. **Target model name** (required). If missing, ask.
2. **Parity strictness.** Ask: *"For the before/after parity check, do you
   want row-count parity only (fast) or full column-hash parity (slower,
   slightly higher warehouse cost)?"* Default: row-count + spot-check hash
   on the grain column and one numeric column.

Do not ask further questions until these two are answered. Then proceed
end-to-end.

**Do NOT ask about saving the report.** The report is always displayed
inline at the end. It is not saved to a file. Persistence is not part of
this skill.

## Procedure

### Phase 1 — Baseline capture (target: ≤3 min)

Before touching anything, capture the baseline. Every number below feeds
the "Before" column of the final report.

Run these steps **in parallel where possible** — most are independent:

1. **Static code metrics** (single bash pass; do not use one call per metric):
   - Total lines, `join` count, CTE count and largest CTE size, count of
     hardcoded literals repeated ≥3 times.
   - Combine into one shell pipeline; do not re-read the file for each
     metric.
2. **Downstream + column-usage map** — delegate to `dbt-analyze`:
   - One call to fetch the downstream subtree and the columns each
     downstream consumes. Save the result. Columns produced by the target
     but not consumed anywhere = "safe to remove" set.
3. **Warehouse baseline snapshot + aggregate signature** — one build, one
   query, one snapshot:
   - `altimate-dbt build --model <target>` (this both proves the current
     state builds and populates the manifest for later parity work).
   - `CREATE OR REPLACE TABLE <db>.<schema>.<target>_before AS SELECT * FROM <target>`.
   - Capture aggregate signature in ONE query:
     `SELECT count(*), count(distinct <grain>), sum(<numeric>), min(<numeric>), max(<numeric>) FROM <target>`.
     This is what parity will re-check in Phase 4.

**Time-saver rule:** do NOT call `cost-report` in Phase 1. Warehouse
signals are collected in Phase 7 only if the user opts in. Pulling
`QUERY_HISTORY` up front bloats the run and most of the time the user
skips warehouse benchmarking anyway.

### Phase 2 — Plan (target: ≤2 min)

Produce a written refactor plan **before** editing any file. The plan must:

- List every proposed new model / macro / var and what logic moves into it.
- Reference the column-usage map from Phase 1 to prove no consumed column
  is being dropped.
- Call out any semantic change explicitly and stop for user confirmation.

Present the plan in **one message**. Wait for approval. Do not proceed to
Phase 3 until the user says go.

### Phase 3 — Execute (target: ≤90s)

Apply the refactor with a **strict write budget**: no more than 5 file
writes total, and NO retries. Get each file right the first time.

1. Create the intermediate models as **ephemeral** (add
   `{{ config(materialized='ephemeral') }}` at the top of each). Ephemeral
   models inline into their consumer at compile time, so no warehouse
   round trip creates them as views. This shaves the second half of the
   parity build.
2. Hoist repeated literals into `vars:` in `dbt_project.yml` (one edit).
3. Rewrite the target as a thin composition. Preserve the final column
   list exactly (order + names + types) (one edit).
4. **Append** schema.yml entries for the new models to the existing
   `models/marts/schema.yml` — do NOT create a new
   `models/intermediate/schema.yml` file. One less file, one less write.
   (Ephemeral models can have descriptions but not tests, which is fine
   for the skill's needs.)

**Compile-check rule:** do NOT run `altimate-dbt compile` in Phase 3 at
all. Go straight to Phase 4's build. If there's a jinja / ref error, the
build will surface it with the same clarity a compile would, and we save
one warehouse round trip.

**Write-budget rule:** if a file needs to be rewritten because your first
version has a syntax or logic problem, that's ONE strike. Two strikes
and you stop — surface the error to the user and ask how to proceed.
Do not silently rewrite the same file three times chasing jinja loop
formatting.

### Phase 4 — Validate parity (target: ≤4 min)

Safety gate. Do not skip.

1. **One build to materialize the new state + downstream:**
   `altimate-dbt build --model +<target>+`. This builds the target plus
   its full upstream and downstream in a single run, which is what we
   need for parity and downstream-still-works evidence in one shot.
2. **Parity via ONE aggregate query** (row-count + spot-check hash):
   `SELECT (SELECT count(*) FROM <target>_before) = (SELECT count(*) FROM <target>) AS row_ok, <sig checks…>`.
   Do NOT call `data_diff` first unless the aggregate check fails. In the
   observed run, `data_diff` needed two retries to resolve identifier
   quoting and warehouse-scoping — skipping it saves 30–60s. Fall back to
   `data_diff` only if the aggregate check disagrees or if the user chose
   full column-hash strictness.
3. If parity-strictness=full, follow the aggregate check with one
   `data_diff` call using **fully qualified UPPERCASE** table names
   (e.g. `ANALYTICS.MARTS.CUSTOMER_ORDER_SUMMARY_BEFORE`) and lowercase
   column names — this matches Snowflake's identifier resolution and
   avoids the two retries observed in the reference run.
4. If parity fails, stop. Skip to Phase 6 with a failure-mode report
   and **do not** replace the production target model. Ask how to proceed.
5. If parity passes, drop the `_before` snapshot.

**Skip rule:** do NOT run per-model `schema-verify` on every touched model
if Phase 4's build already succeeded — `build` runs schema-verify
internally. Run schema-verify only on the target model, once, and only if
the user asked for strict verification. In the observed run, five
per-model schema-verify calls each reported "mismatch" purely because
`schema.yml` documents a curated subset — five calls to learn nothing.
Skip them.

### Phase 5 — Static-only optimization signals (target: ≤1 min)

**Always run — no warehouse required.** Delegate to `sql-review` on the
refactored target model to catch remaining lint / anti-patterns.

Do NOT apply findings automatically. Filter out warnings that match
project-wide conventions (e.g., `SELECT *` in import CTEs — the whole
staging layer uses this pattern; flagging it in the refactored model
would be noise). Capture surviving high-severity items into the "Next-step
optimizations" section of the report.

### Phase 6 — Compose and display the report (target: ≤2 min)

Displaying the report is the payoff. Always display it inline in chat
using the exact structure below. Numbers must be real (from Phases 1–5).

**Never save the report to a file. Do not ask about saving it.** The
report lives in the conversation.

Structure:

```
# Refactor Report — <target model>

Date: <YYYY-MM-DD>
Target: <name>   Downstream consumers: <n> (<list>)   Parity: PASSED | FAILED

## Bottleneck summary (before)
<2–4 sentence prose paragraph naming the top ~3 things that made the model
painful. Concrete: "the customer_order_history CTE was 48 lines and mixed
recency, frequency, monetary and tenure logic — any change required
re-reasoning about all four dimensions at once. Payment pivot logic was
duplicated from orders.sql. Segment thresholds appeared as inline literals
in 8 places, so a threshold change meant editing SQL in 8 spots without
any single source of truth." No jargon, no marketing tone.>

## Outcome axes improved
| Axis                          | Improved? | Why (short, concrete) |
|-------------------------------|-----------|-----------------------|
| Readability                   | Yes / No  | e.g. "target model 206 → 82 lines; each intermediate has one job" |
| Maintainability               | Yes / No  | e.g. "threshold changes now touch 1 line in dbt_project.yml, not 8 places in SQL" |
| Reusability                   | Yes / No  | e.g. "int_order_payments_pivot now available to any downstream that needs order-level payment breakdown" |
| Performance (static evidence) | Yes / No / Not measured | e.g. "removed 2 correlated subqueries and one self-join predicate that scanned raw_orders twice per customer; runtime measurement gated behind warehouse benchmark" |
| Cost (static evidence)        | Yes / No / Not measured | e.g. "same as above; credits impact measurable via Phase 7" |
| Governance / testability      | Yes / No  | e.g. "each intermediate now has unique/not_null tests on its grain key — 4 new tests, none before" |
| Best-practice compliance      | Yes / No  | e.g. "matches dbt Labs' recommended staging → intermediate → mart layering; hardcoded literals hoisted to vars" |
| Semantic behavior             | Preserved | Row count and aggregate signature identical (see Parity evidence below) |

Fill only rows that materially changed. Mark "Not measured" honestly for
performance and cost when warehouse benchmark was skipped — do not claim
performance improvements without measurement.

## Code-shape metrics

| Metric                             | Before | After | Δ |
|------------------------------------|--------|-------|---|
| Lines in target model              |        |       |   |
| Joins in target model              |        |       |   |
| CTEs in target model               |        |       |   |
| Largest CTE (lines)                |        |       |   |
| Repeated hardcoded literals        |        |       |   |
| Total models in refactor scope     |        |       |   |
| Columns removed (unused downstream)|   —    |       |   |

## Parity evidence
- Row count before: <n>   after: <n>
- Aggregate signature (count / sum / min / max on grain + one numeric):
  before → after (identical | mismatch on <col>)
- `data_diff` result (if run): <n rows mismatched>
- Full project build after refactor: PASS=<n> ERROR=<n> WARN=<n>

## Next-step optimizations (not applied)
- <bullet per surviving sql-review finding>
- <bullet per opportunity noted during refactor but out of scope>

## Files changed
- <path> — created / modified

---

Would you like to run a **warehouse benchmark** now to measure real
runtime, bytes scanned, and credits — comparing the refactored model
against its historical query stats? (This uses `cost-report` + a fresh
run of the new model. Takes 2–3 min extra and requires the project's
warehouse credentials to be reachable.)
```

The trailing question triggers Phase 7. Do not run Phase 7 until the user
says yes.

### Phase 7 — (Optional) Snowflake warehouse benchmark on real history

Run only if the user answers "yes" to the trailing question in Phase 6.
Otherwise the run ends after Phase 6.

Ask the follow-ups only now:
- *"Which warehouse profile / target should I use?"* (default: the `dev`
  target in `profiles.yml`)
- *"How many days of query history should I compare against?"* (default:
  30)

**Snowflake query-history sources — pick the right one for each side of
the comparison.** Snowflake exposes query history in two places, and
this skill uses them **together**:

| Source | Latency | Retention | Use for |
|---|---|---|---|
| `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` | 20–45 min | 365 days | **Historical "before"** — averages over the last N days |
| `INFORMATION_SCHEMA.QUERY_HISTORY_BY_WAREHOUSE()` table function | ~seconds | 7 days, 10K rows/call | **Fresh "after"** — the run we just triggered |

`ACCOUNT_USAGE` is the only source with enough retention to give a
credible historical baseline, but its ~45 min ingestion lag means a run
triggered inside the demo will NOT be visible there in time. The
`INFORMATION_SCHEMA` table function is near-realtime but capped at 7 days
of history. Using both sidesteps both limits.

Then:

1. **Historical baseline** — delegate to `cost-report` (which reads
   `ACCOUNT_USAGE.QUERY_HISTORY`) scoped to the target model over the
   requested window. Capture avg runtime, p95 runtime, avg bytes scanned,
   credits over the window, run frequency. This is the "Historical avg"
   column of the report.

   *If `cost-report` returns zero rows* (model never ran in prod, or
   `ACCOUNT_USAGE` grants missing), stop and tell the user: warehouse
   benchmark needs a historical baseline. Do not fabricate a "before"
   from a single fresh run of the old code.

2. **Fresh refactored run** — trigger one build of the refactored model
   at the top of Phase 7:
   `altimate-dbt build --model <target>` and capture the `QUERY_ID` from
   the build's compiled-query log line (dbt writes it as
   `/* {"app": "dbt", ..., "query_id": "01b..."} */` in the trailing
   comment, or you can read the dbt log's `SUCCESS` line for the runtime
   directly).

   Then read the fresh run's metrics from `INFORMATION_SCHEMA`:

   ```sql
   SELECT
       execution_time / 1000 AS runtime_s,
       bytes_scanned,
       credits_used_cloud_services,
       warehouse_size
   FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_WAREHOUSE(
       WAREHOUSE_NAME => '<warehouse>',
       RESULT_LIMIT => 100
   ))
   WHERE query_text ILIKE '%<target>%'
     AND query_text NOT ILIKE '%INFORMATION_SCHEMA%'
     AND start_time >= dateadd('minute', -10, current_timestamp)
   ORDER BY start_time DESC
   LIMIT 1;
   ```

   There is usually a 1–5s gap between build completion and
   `INFORMATION_SCHEMA` visibility. If the first call returns zero rows,
   retry ONCE after a 5-second wait. If still zero, fall back to the
   runtime the dbt log itself reported (`SUCCESS 1 in Xs`) and mark
   `bytes_scanned` as "not captured".

   **Do NOT read the fresh run from `ACCOUNT_USAGE`.** It will not be
   there for ~45 min and the demo will look broken.

3. **Optimization signals** — delegate to `query-optimize` on the
   refactored SQL for additional optimizations the cleaner structure now
   enables (typically: incremental candidacy). Do NOT apply — add to
   "Next-step optimizations" in the report.

4. **Append a warehouse-metrics block** to the previously-displayed
   report (do not re-display the whole report — just append):

   ```
   ## Warehouse metrics
   Historical baseline: last <N> days from ACCOUNT_USAGE.QUERY_HISTORY (n=<run count>)
   Fresh refactored run: 1 run just now, read from INFORMATION_SCHEMA (~s latency)

   | Metric                         | Historical avg | Refactored run | Δ |
   |--------------------------------|----------------|----------------|---|
   | Runtime (s)                    |                |                |   |
   | Bytes scanned                  |                |                |   |
   | Credits per run (est.)         |                |                |   |
   | Estimated annual savings (USD) |     —          |                |   |
   ```

   Cite both sources explicitly in the block header so anyone reading
   the report understands why "before" is an average and "after" is a
   single run.

   Then update the "Outcome axes improved" rows for Performance and Cost
   from "Not measured" to Yes/No with the measured numbers.

## Tool delegation cheatsheet

| Need                                    | Call                                          |
|-----------------------------------------|-----------------------------------------------|
| Downstream tree + column usage          | `dbt-analyze` (once, in Phase 1)              |
| Compile / build a model                 | `dbt-develop` → `altimate-dbt compile/build`  |
| Row-count + hash parity                 | Aggregate SQL first; `data-parity` only on mismatch or full-strictness |
| Warehouse cost baseline                 | `cost-report` (Phase 7 only)                  |
| Per-query performance rewrite candidates| `query-optimize` (Phase 7 only)               |
| Column-level lineage diff (old vs new)  | `lineage-diff` (only if the user asks)        |
| Static SQL anti-pattern lint            | `sql-review` (Phase 5)                        |
| Verify materialized schema matches yml  | `dbt-schema-verify` (target only, once, only if strict verification requested) |

Do **not** grep for lineage, parse SQL by hand, or shell out to `dbt`
directly if an Altimate skill exists for the task. The Altimate skills
handle jinja / incremental / macro edge cases that ad-hoc scripts miss.

## Efficiency rules (learned from prior runs)

These exist to hold the 20-minute budget:

- **Parallelize Phase 1** — static metrics, `dbt-analyze`, and the baseline
  build are independent; issue them together.
- **Zero compiles in Phase 3.** Go straight to Phase 4's build — same
  error surface, one fewer round trip.
- **Ephemeral intermediates.** Materialize new intermediate models as
  ephemeral so they inline into the target at compile time. No separate
  warehouse round trip creates them as views.
- **Max 5 file writes in Phase 3, no retries.** Two failed attempts on
  the same file = stop and ask.
- **One build for parity** (`build --model +<target>+`), which also
  exercises downstream — do not do a target-only build followed by a
  full-project build.
- **Aggregate SQL check before `data_diff`.** `data_diff` needs UPPERCASE
  fully-qualified names and lowercase column names on Snowflake; the
  aggregate SQL avoids the retry cycle when nothing has changed.
- **No per-model `schema-verify` fan-out** when `build` already succeeded.
  It reports "mismatch" for any partial `schema.yml` documentation — the
  false-positive rate is high and the information gained is low.
- **Do not pull `QUERY_HISTORY` up front.** Warehouse work is Phase 7,
  gated behind opt-in.
- **In Phase 7, read historical from `ACCOUNT_USAGE`, fresh from
  `INFORMATION_SCHEMA`.** `ACCOUNT_USAGE` has ~45 min ingestion lag — a
  fresh run triggered inside the demo will not appear in time.
  `INFORMATION_SCHEMA.QUERY_HISTORY_BY_WAREHOUSE()` returns in seconds
  but only holds 7 days. Use both.
- **Do not re-read files you already read.** Cache metrics as text; do
  not re-invoke `read` to pull line counts you already computed.

## Behavior contract

- Never modify a model without first capturing its baseline.
- Never delete a column without confirming it is not consumed downstream.
- Never claim "safe" without a passing parity check.
- Always display the report inline — even on failure. The report is the
  demonstrable artifact.
- Never save the report to a file. Never ask about saving it.
- Never claim measured performance / cost improvements without a Phase 7
  warehouse benchmark. Use "Not measured" honestly if Phase 7 was skipped.
