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
   - **Resolve the materialized relation from the dbt manifest**
     (`target/manifest.json` → `nodes.<model>.relation_name`), do NOT
     assume it lives in the session's current database/schema. Use that
     fully-qualified name as `<src_relation>` below.
   - Snapshot to a **session-unique, non-colliding** name — include the
     dbt invocation_id or a timestamp suffix so a second concurrent run
     does not clobber the first:
     `CREATE TABLE <db>.<schema>.<target>_before_<yyyymmdd_hhmmss> AS SELECT * FROM <src_relation>`.
     Use `CREATE TABLE` (not `CREATE OR REPLACE`); if the name collides,
     surface the error — do not silently overwrite another user's snapshot.
   - Capture aggregate signature in ONE query, built dynamically from the
     model's actual column list (also in `manifest.json`):
     `SELECT count(*), count(distinct <grain>) [, sum(<n>), min(<n>), max(<n>) FOR EACH numeric column <n>] FROM <src_relation>`.
     If the model has **no numeric columns** (pure dimension model),
     skip the sum/min/max terms — the key-wise comparison in Phase 4
     is the real safety net. This signature is cheap context, not the
     parity gate.

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

   **Incremental-model exception.** If the target is `materialized='incremental'`,
   do NOT extract any CTE that uses `{{ this }}`, `is_incremental()`, or
   references the target's own prior state into an ephemeral model.
   `is_incremental()` evaluates against the **ephemeral** model's own
   context (always false), silently stripping the incremental filter and
   causing the next build to reinsert all historical rows on an `append`
   target. For incremental targets: keep materialization-dependent
   predicates in the target model itself and extract only pure, stateless
   logic (joins, aggregations that don't reference `this`). Call this out
   explicitly in the Phase 2 plan.
2. Hoist repeated literals into `vars:` in `dbt_project.yml` (one edit).
3. Rewrite the target as a thin composition. Preserve the final column
   list exactly (order + names + types) (one edit).
4. **Append** schema entries for the new models to the project's existing
   properties file. **Discover the file first** — dbt projects use
   different conventions:
   - A single `models/<layer>/schema.yml` co-located with models
   - A sibling `properties.yml` or `_models.yml`
   - Per-model `<model_name>.yml` next to the `.sql`
   Pick the file that already documents a sibling model in the same
   layer. Only create a new properties file if no existing one applies.
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

1. **Build the refactored candidate in an isolated schema, NOT in prod.**
   The production target must remain the current version until parity
   passes. Options, in order of preference:
   - Use a non-prod dbt target (e.g. `--target dev` with
     `generate_schema_name` giving a user-specific schema).
   - Or set a one-off suffix via `--vars '{candidate_suffix: _candidate}'`
     combined with a project macro that honors it.
   - Or run `dbt run-operation` to materialize into a scratch schema
     the user controls.

   Invocation (adjust to the project's convention):
   `altimate-dbt build --model +<target>+ --target <non_prod_target>`.
   This builds the target plus its full upstream and downstream in a
   single run, giving us parity + downstream-still-works evidence in one
   shot — WITHOUT overwriting the production relation.

   If the project has no non-prod target configured, **stop and ask the
   user how to proceed**. Do not fall through to a prod build.
2. **Parity gate — key-wise comparison is the baseline, not aggregates.**
   Aggregates (count/sum/min/max) do NOT detect value swaps between keys
   or changes to non-numeric columns. Run `data_diff` (or an equivalent
   key-wise EXCEPT-based check) as the primary gate:

   ```sql
   -- Key-wise: every grain key in before must appear in after with
   -- identical values across all columns. Both directions.
   SELECT 'rows_only_in_before' AS side, count(*) AS n FROM (
     SELECT * FROM <before_relation> EXCEPT SELECT * FROM <candidate_relation>
   )
   UNION ALL
   SELECT 'rows_only_in_after', count(*) FROM (
     SELECT * FROM <candidate_relation> EXCEPT SELECT * FROM <before_relation>
   );
   ```

   Both counts MUST be 0 for parity to pass. Aggregate signature from
   Phase 1 is useful supporting evidence in the report but is NOT the
   gate. If the user explicitly chose "row-count-only" strictness, run
   the row-count check and label parity in the report as
   `AGGREGATE-ONLY (per-row not verified)` — never claim full parity
   from an aggregate match.
3. **Use the manifest-resolved identifiers verbatim.** Snowflake treats
   quoted identifiers as case-sensitive; forcing UPPERCASE breaks projects
   that create quoted lowercase relations (e.g. `"customer_order_summary"`).
   Pass the fully-qualified `relation_name` straight from `target/manifest.json`
   (which already contains the correct quoting the adapter used at build
   time). Do not re-case or re-quote.
4. If parity fails, stop. Skip to Phase 6 with a failure-mode report
   and **do not** promote the candidate relation. Keep the `_before`
   snapshot for debugging. Ask how to proceed.
5. If parity passes, promote the candidate: either `ALTER TABLE ... RENAME`
   or re-run the build against the prod target. Then drop the `_before`
   snapshot and the candidate relation.

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
| Semantic behavior             | Preserved / Not preserved / Aggregate-only verified | Fill from Parity evidence below. "Preserved" ONLY when the key-wise EXCEPT comparison returned 0 mismatches in both directions. "Not preserved" when parity failed. "Aggregate-only verified" when the user chose row-count/aggregate-only strictness. |

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
- Key-wise EXCEPT comparison: <n> rows only in before, <n> rows only in after
  (both must be 0 for PASSED)
- Aggregate signature (count / distinct grain / sum·min·max on numerics if present):
  before → after (identical | mismatch on <col>)  — supporting evidence only, not the gate
- Target-lineage build (`build +<target>+`) after refactor: PASS=<n> ERROR=<n> WARN=<n>
  (scope: target plus its ancestors and descendants, not the whole project)

## Next-step optimizations (not applied)
- <bullet per surviving sql-review finding>
- <bullet per opportunity noted during refactor but out of scope>

## Files changed
- <path> — created / modified

---

<ONLY IF Parity: PASSED, append the following question. OMIT entirely on
Parity: FAILED — do not invite a warehouse benchmark against a refactor
that didn't pass semantic parity.>

Would you like to run a **warehouse benchmark** now to measure real
runtime, bytes scanned, and credits — comparing the refactored model
against its historical query stats? (This uses `cost-report` + a fresh
run of the new model. Takes 2–3 min extra and requires the project's
warehouse credentials to be reachable.)
```

The trailing question triggers Phase 7. Do not run Phase 7 until the user
says yes. On parity failure, the report ends after "Files changed" and
the next step is remediation, not benchmarking.

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
| `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` | 20–45 min | 365 days | **Historical "before"** — runtime / bytes averages over the last N days |
| `SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY` | 20–45 min + | 365 days | **Compute credits attributed to a query** (both historical and fresh, once ingested) — the only correct source for warehouse-compute credits |
| `INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION()` / `BY_WAREHOUSE()` | ~seconds | 7 days, 10K rows/call | **Fresh "after"** — runtime + bytes_scanned for the run we just triggered, filtered by `QUERY_ID` |

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
   **on the user-selected profile/target** (do not drop the `--target`
   argument; otherwise the build goes to the default connection and the
   history lookup finds nothing or compares the wrong environment):

   `altimate-dbt build --model <target> --target <selected_target>`

   **Capture the executed statement's `QUERY_ID` from the adapter's
   query log, not from the compiled SQL** — Snowflake assigns the
   `QUERY_ID` server-side when the statement runs, so it cannot appear
   in the compiled SQL beforehand. Sources, in order of preference:
   - dbt's `logs/dbt.log` (DEBUG level): the adapter logs each
     statement's `query_id` after Snowflake returns it.
   - `run_results.json` (newer dbt versions include `adapter_response.query_id`
     per node).
   - As a fallback: query `INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION()`
     filtered to the dbt session's statements that materialize the target
     (statement type `CREATE_TABLE_AS_SELECT` / `INSERT` touching the
     target relation name).

   Note: a `dbt build` run of a single model typically issues several
   statements (schema create, model materialize, tests). The one we want
   is the model's materialize statement — not a `dbt test` statement that
   also references the model name. Filtering by `QUERY_ID` avoids this
   ambiguity; filtering by `ILIKE '%<target>%'` does not.

   Then read the fresh run's metrics from `INFORMATION_SCHEMA` by
   `QUERY_ID`:

   ```sql
   SELECT
       execution_time / 1000.0 AS runtime_s,
       bytes_scanned,
       warehouse_size,
       warehouse_name
   FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION(
       RESULT_LIMIT => 1000
   ))
   WHERE query_id = '<captured_query_id>';
   ```

   (Use `QUERY_HISTORY_BY_SESSION` within the same session, or
   `QUERY_HISTORY_BY_WAREHOUSE` filtered by `QUERY_ID` from a different
   session — never filter solely by `query_text ILIKE`.)

   There is usually a 1–5s gap between statement completion and
   `INFORMATION_SCHEMA` visibility. If the first call returns zero rows,
   retry ONCE after a 5-second wait. If still zero, fall back to the
   runtime the dbt log itself reported (`SUCCESS 1 in Xs`) and mark
   `bytes_scanned` as "not captured".

   **Compute credits for the fresh run** — do NOT use
   `credits_used_cloud_services`; that column measures metadata/cloud
   services credits, which are typically ~0 for compute-bound workloads
   and will make genuine warehouse-cost wins look like zero savings.
   Use `SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY.CREDITS_ATTRIBUTED_COMPUTE`
   filtered by `QUERY_ID` (same column the existing `cost-report` skill
   uses). If `QUERY_ATTRIBUTION_HISTORY` hasn't caught up yet (same
   ~45 min lag as `ACCOUNT_USAGE`), mark the fresh-run credits and
   savings as "not yet available — rerun this cell in ~1 hour" rather
   than filling in a cloud-services number.

   **Do NOT read the fresh run's runtime/bytes from `ACCOUNT_USAGE`.**
   It will not be there for ~45 min. `INFORMATION_SCHEMA` is correct for
   runtime and bytes_scanned; `ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY`
   is the only source for the compute-attributed credits number.

3. **Optimization signals** — delegate to `query-optimize` on the
   refactored SQL for additional optimizations the cleaner structure now
   enables (typically: incremental candidacy). Do NOT apply — add to
   "Next-step optimizations" in the report.

4. **Append a warehouse-metrics block** to the previously-displayed
   report (do not re-display the whole report — just append):

   ```
   ## Warehouse metrics
   Historical baseline: last <N> days from ACCOUNT_USAGE.QUERY_HISTORY +
     QUERY_ATTRIBUTION_HISTORY (n=<run count>)
   Fresh refactored run: 1 run just now (QUERY_ID=<id>), runtime/bytes
     from INFORMATION_SCHEMA (~s latency); attributed compute credits
     from QUERY_ATTRIBUTION_HISTORY (available after ~45 min)

   | Metric                              | Historical avg | Refactored run | Δ |
   |-------------------------------------|----------------|----------------|---|
   | Runtime (s)                         |                |                |   |
   | Bytes scanned                       |                |                |   |
   | Credits per run (compute-attributed)|                | <value or "pending ingestion"> |   |
   | Estimated annual savings (USD)      |     —          | <computed once credits available> |   |
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
- **One build for parity** (`build --model +<target>+ --target <non_prod>`),
  which also exercises downstream — do not do a target-only build followed
  by a full-project build. **Always on a non-prod target** to avoid
  writing an unverified refactor over the production relation.
- **Key-wise parity is the gate, aggregates are supporting evidence.**
  Aggregates (count/sum/min/max) miss value swaps between keys and
  non-numeric changes. Use the two-direction `EXCEPT` comparison from
  Phase 4 as the pass/fail signal. Pass identifiers through from
  `manifest.json` verbatim — do not re-case or re-quote them.
- **No per-model `schema-verify` fan-out** when `build` already succeeded.
  It reports "mismatch" for any partial `schema.yml` documentation — the
  false-positive rate is high and the information gained is low.
- **Do not pull `QUERY_HISTORY` up front.** Warehouse work is Phase 7,
  gated behind opt-in.
- **In Phase 7, split by metric and by freshness.** Historical runtime /
  bytes / credits come from `ACCOUNT_USAGE.QUERY_HISTORY` +
  `QUERY_ATTRIBUTION_HISTORY`. Fresh runtime + bytes come from
  `INFORMATION_SCHEMA` filtered by captured `QUERY_ID` (not by
  `query_text ILIKE`, which can match a `dbt test` statement or another
  session's query). Fresh **compute credits** can only come from
  `QUERY_ATTRIBUTION_HISTORY` once it ingests (~45 min); mark as
  "pending ingestion" until then rather than substituting
  `credits_used_cloud_services`, which measures a different thing.
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
