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

## Prerequisites & invocation

This skill delegates specialized sub-tasks (lineage, parity, SQL review,
cost attribution, etc.) that are not themselves packaged with
`snowflake-skills`. Two valid invocation paths — pick the one that
matches the user's environment:

**Preferred — `altimate-code`** (bundled in the `dbt-snowflake` kit).
Before using any delegated-task line below, verify it is available:

```bash
command -v altimate-code
```

If present, delegate each sub-task via its non-interactive runner:

```bash
altimate-code run "<task description>" --yolo \
  --output /tmp/altimate-result.md --dir "$(pwd)"
```

Then read `/tmp/altimate-result.md` and use the result. See the
`altimate-code` skill for the full flag reference and install guidance.

**Fallback — plain dbt + direct SQL** when `altimate-code` is not
installed and the user does not want to install it. In that case:

- Replace `dbt-analyze` lookups with `dbt ls --select +<target>+ --output json`
  (downstream nodes) plus `dbt docs generate` + reading
  `target/catalog.json` and `target/manifest.json` for the column-usage
  map. Note: this is coarser than altimate-code's column-level lineage.
- Replace build/compile delegation with plain `dbt build` / `dbt compile`.
- Replace `data-parity` with the SQL in Phase 4 run directly against the
  warehouse (via the dbt adapter, `snowsql`, or any Snowflake client).
- Replace `sql-review` with `sqlfluff lint` or project-standard linter.
- Replace `cost-report` / `query-optimize` with direct queries against
  `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` + `QUERY_ATTRIBUTION_HISTORY`
  (sample SQL in Phase 7).

If **neither** `altimate-code` nor plain `dbt` is available, stop and
tell the user — do not fabricate results from file reads alone.

Throughout the procedure below, every reference to a delegated tool
(`dbt-analyze`, `data-parity`, `sql-review`, `cost-report`,
`query-optimize`, `lineage-diff`) is a logical sub-task name. Execute it
via `altimate-code run "..."` on the preferred path or the plain-dbt
equivalent on the fallback path. Every reference to `altimate-dbt build
--model X` on the preferred path translates to `altimate-code run "dbt
build --select X ..."` or plain `dbt build --select X` on the fallback
path.

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
2. **Downstream + column-usage map** — delegate (see tool-delegation
   cheatsheet):
   - One call to fetch the downstream dbt subtree and the columns each
     downstream dbt model consumes. Save the result. Columns produced by
     the target but not referenced by any downstream dbt node = the
     **"candidates for review"** set — NOT "safe to remove".
   - The dbt graph can only see dbt-tracked consumers. It is blind to
     BI dashboards, direct warehouse queries, reverse-ETL jobs, external
     tools, and anything that reads the materialized relation outside of
     `ref()`. Removing a column that is unreferenced in dbt can still
     break those consumers.
   - Default behavior: **do not drop any columns** in the refactor
     without explicit per-column user confirmation during Phase 2. The
     candidates set is information for the plan, not a license to delete.
3. **Warehouse baseline snapshot + aggregate signature** — one build, one
   query, one snapshot:
   - `dbt build --select <target>` (or `altimate-code run "dbt build --select <target>"` on the preferred path) (this both proves the current
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

Apply the refactor **strictly within the write set approved in the
Phase 2 plan**: one write per file enumerated in the plan (new ephemeral
intermediates, the rewritten target, `dbt_project.yml` var hoists, one
properties-file append). Do not create or modify any file that was not
in the approved plan. The budget scales with the plan — three extracted
CTEs is three intermediate writes, not a cap violation.

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

**Compile-check rule:** do NOT run a separate `dbt compile` in Phase 3.
Go straight to Phase 4's build. If there's a jinja / ref error, the
build will surface it with the same clarity a compile would, and we save
one warehouse round trip.

**No silent retries.** If a file needs to be rewritten because your
first version has a syntax or logic problem, that is ONE strike. Two
strikes on the same file and you stop — surface the error to the user
and ask how to proceed. Do not silently rewrite the same file three
times chasing jinja loop formatting. This discipline is independent of
the write-set size.

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
   `dbt build --select +<target>+ --target <non_prod_target>` (or route
   via `altimate-code run "..."` on the preferred path).
   This builds the target plus its full upstream and downstream in a
   single run, giving us parity + downstream-still-works evidence in one
   shot — WITHOUT overwriting the production relation.

   If the project has no non-prod target configured, **stop and ask the
   user how to proceed**. Do not fall through to a prod build.
2. **Parity gate — multiplicity-aware comparison, not just EXCEPT.**
   Aggregates (count/sum/min/max) do NOT detect value swaps between keys
   or changes to non-numeric columns. Plain `EXCEPT` is also insufficient
   on Snowflake because it eliminates duplicates: a fan-out join that
   turns `{A, A, B}` into `{A, B, B}` leaves the distinct-row sets
   identical and both `EXCEPT` sides return 0 — parity would falsely
   pass despite a changed row count and shifted multiplicities.

   Run the gate as **two independent checks**, both must pass:

   ```sql
   -- (a) Row-count equality — catches any size change,
   --     including same-set-with-different-multiplicities cases that
   --     EXCEPT alone misses.
   SELECT
     (SELECT count(*) FROM <before_relation>)    AS before_rows,
     (SELECT count(*) FROM <candidate_relation>) AS after_rows,
     (SELECT count(*) FROM <before_relation>)
       = (SELECT count(*) FROM <candidate_relation>) AS row_count_ok;

   -- (b) Multiplicity-aware set comparison — GROUP BY all columns and
   --     compare per-row counts across sides via FULL OUTER JOIN. Any
   --     missing row, extra row, or multiplicity shift surfaces as a
   --     row where before_cnt <> after_cnt (or one side is NULL).
   --
   --     NULL-safety: USING (...) and ON a.c = b.c both treat NULL as
   --     non-matching (NULL = NULL -> UNKNOWN), so identical rows that
   --     contain NULL in any joined column would fail to pair up and
   --     register as false "differing rows". Match on
   --     `a.c IS NOT DISTINCT FROM b.c` for every column — that returns
   --     TRUE when both sides are NULL and when both sides are equal.
   WITH b AS (
     SELECT <col_list>, count(*) AS cnt FROM <before_relation>    GROUP BY <col_list>
   ),
   a AS (
     SELECT <col_list>, count(*) AS cnt FROM <candidate_relation> GROUP BY <col_list>
   )
   SELECT count(*) AS differing_rows
   FROM b
   FULL OUTER JOIN a
     ON  a.<col_1> IS NOT DISTINCT FROM b.<col_1>
     AND a.<col_2> IS NOT DISTINCT FROM b.<col_2>
     AND /* …one row per column in <col_list>… */
     AND a.<col_N> IS NOT DISTINCT FROM b.<col_N>
   WHERE coalesce(b.cnt, 0) <> coalesce(a.cnt, 0);
   ```

   Parity passes **only if both** `row_count_ok = TRUE` **and**
   `differing_rows = 0`. If the user explicitly chose row-count-only
   strictness, run (a) alone and label parity in the report as
   `ROW-COUNT-ONLY (per-row not verified)` — never claim full parity
   from a row-count match. Aggregate signature from Phase 1 is useful
   supporting evidence in the report but is NOT the gate.

   The `<col_list>` is the model's full column list from
   `manifest.json`'s `nodes.<model>.columns`; expand it inline (both in
   the `GROUP BY` and in the per-column `IS NOT DISTINCT FROM` conditions)
   rather than using `GROUP BY *` or `USING (...)` — Snowflake does not
   accept `*` in `GROUP BY`, and `USING (...)` is not NULL-safe.
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

6. **Column-contract check.** `dbt build` does NOT verify the physical
   column list — it only runs the tests you declared in `schema.yml`.
   A refactor can change a column's name, order, or type while row count
   and tests still pass. Compare the before/after output schemas
   explicitly, independent of the build result:

   ```sql
   SELECT
     coalesce(b.column_name, a.column_name) AS column_name,
     b.ordinal_position AS before_pos, a.ordinal_position AS after_pos,
     b.data_type        AS before_type, a.data_type        AS after_type,
     CASE
       WHEN b.column_name IS NULL              THEN 'ADDED'
       WHEN a.column_name IS NULL              THEN 'REMOVED'
       WHEN b.data_type <> a.data_type         THEN 'TYPE_CHANGED'
       WHEN b.ordinal_position <> a.ordinal_position THEN 'ORDER_CHANGED'
       ELSE 'OK'
     END AS status
   FROM
     (SELECT column_name, ordinal_position, data_type
      FROM <db>.INFORMATION_SCHEMA.COLUMNS
      WHERE table_schema = '<before_schema>' AND table_name = '<before_table>') b
   FULL OUTER JOIN
     (SELECT column_name, ordinal_position, data_type
      FROM <db>.INFORMATION_SCHEMA.COLUMNS
      WHERE table_schema = '<candidate_schema>' AND table_name = '<candidate_table>') a
     USING (column_name)
   ORDER BY coalesce(b.ordinal_position, a.ordinal_position);
   ```

   Any row with `status <> 'OK'` means the Phase 3 "preserve final
   column list exactly (order + names + types)" rule was violated.
   Fail parity and surface the diff. The old per-model schema-verify
   fan-out is still noisy against partial `schema.yml` documentation —
   this `INFORMATION_SCHEMA`-based check compares the materialized
   relations directly, which is what the contract actually requires.

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
| Semantic behavior             | Preserved / Not preserved / Row-count-only verified | Fill from Parity evidence below. "Preserved" ONLY when ALL THREE Phase 4 gates passed: row-count equality, multiplicity-aware NULL-safe comparison (`differing_rows = 0`), AND column-contract diff (0 columns with `status <> 'OK'`). The column-contract gate matters even when values compare equal — e.g. a `NUMBER → FLOAT` type change can keep `differing_rows = 0` under implicit coercion while still breaking the column contract. "Not preserved" when ANY of the three failed. "Row-count-only verified" when the user chose row-count-only strictness; the column-contract diff (Phase 4 step 6) still runs unconditionally in this mode, so it must also be passing — only the per-row multiplicity comparison is skipped. |

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
- Row count: before=<n>, after=<n>, equal=<TRUE|FALSE> (must be TRUE for PASSED)
- Multiplicity-aware NULL-safe comparison: differing_rows=<n> (must be 0 for PASSED)
- Column-contract diff (INFORMATION_SCHEMA.COLUMNS): <n> columns with status <> 'OK'
  (must be 0 for PASSED; any ADDED / REMOVED / TYPE_CHANGED / ORDER_CHANGED fails parity)
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

   `dbt build --select <target> --target <selected_target>` (or
   `altimate-code run "dbt build --select <target> --target <selected_target>"`
   on the preferred path).

   **Capture the executed statement's `QUERY_ID` from the adapter's
   query log, not from the compiled SQL** — Snowflake assigns the
   `QUERY_ID` server-side when the statement runs, so it cannot appear
   in the compiled SQL beforehand. Sources, in order of preference:
   - dbt's `logs/dbt.log` (DEBUG level): the adapter logs each
     statement's `query_id` after Snowflake returns it.
   - `run_results.json` (newer dbt versions include `adapter_response.query_id`
     per node).
   - As a fallback: query `INFORMATION_SCHEMA.QUERY_HISTORY_BY_WAREHOUSE()`
     filtered to recent `CREATE_TABLE_AS_SELECT` / `INSERT` statements on
     the warehouse that touch the target relation name, then pick the
     one whose timing matches the dbt run. Do NOT use
     `QUERY_HISTORY_BY_SESSION()` here — the dbt build ran in a separate
     process/session, so a `BY_SESSION` call from this skill's session
     returns nothing.

   Note: a `dbt build` run of a single model typically issues several
   statements (schema create, model materialize, tests). The one we want
   is the model's materialize statement — not a `dbt test` statement that
   also references the model name. Filtering by `QUERY_ID` avoids this
   ambiguity; filtering by `ILIKE '%<target>%'` does not.

   Then read the fresh run's metrics from `INFORMATION_SCHEMA` by
   `QUERY_ID`. Use `QUERY_HISTORY_BY_WAREHOUSE` (the dbt build ran in
   a different session, so `BY_SESSION` would return nothing):

   ```sql
   SELECT
       execution_time / 1000.0 AS runtime_s,
       bytes_scanned,
       warehouse_size,
       warehouse_name
   FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_WAREHOUSE(
       WAREHOUSE_NAME => '<warehouse_from_selected_target>',
       RESULT_LIMIT => 1000
   ))
   WHERE query_id = '<captured_query_id>';
   ```

   Never filter solely by `query_text ILIKE` — that can match a `dbt test`
   statement or another session's query. Always filter by the captured
   `QUERY_ID`.

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

Columns show the preferred invocation (via `altimate-code run`) and the
plain-dbt fallback. See "Prerequisites & invocation" above for which to
use.

| Need | Preferred (`altimate-code run "..."`) | Fallback |
|------|---------------------------------------|----------|
| Downstream tree + column usage (Phase 1) | `altimate-code run "map downstream consumers and column usage for model <target>"` | `dbt ls --select +<target>+ --output json` + parse `target/catalog.json` |
| Compile / build a model | `altimate-code run "dbt build --select <target> --target <t>"` | `dbt build --select <target> --target <t>` |
| Row-count + multiplicity-aware parity (Phase 4) | Run the SQL in Phase 4 directly via `altimate-code run "<sql>"` or any Snowflake client | Same SQL via `dbt --quiet show`, `snowsql`, or Python/SQL client |
| Warehouse cost baseline (Phase 7) | `altimate-code run "cost report for model <target> over last <N> days"` | Direct SQL on `ACCOUNT_USAGE.QUERY_HISTORY` + `QUERY_ATTRIBUTION_HISTORY` |
| Per-query optimization suggestions (Phase 7) | `altimate-code run "suggest query optimizations for <target>"` | Manual review + `EXPLAIN` plan reading |
| Column-level lineage diff (old vs new) | `altimate-code run "column lineage diff for <target> between <before_relation> and <candidate_relation>"` | Not easily reproducible without altimate-code; skip or ask the user |
| Static SQL anti-pattern lint (Phase 5) | `altimate-code run "sql-review on models/.../<target>.sql"` | `sqlfluff lint models/.../<target>.sql` |
| Column-contract check (Phase 4, step 6) | Run the `INFORMATION_SCHEMA.COLUMNS` SQL in Phase 4 via `altimate-code run` or any Snowflake client | Same SQL via any Snowflake client |

Do **not** grep for lineage or parse SQL by hand when a tool exists for
the task. Jinja / incremental / macro edge cases are easy to miss with
ad-hoc scripts.

## Efficiency rules (learned from prior runs)

These exist to hold the 20-minute budget:

- **Parallelize Phase 1** — static metrics, `dbt-analyze`, and the baseline
  build are independent; issue them together.
- **Zero compiles in Phase 3.** Go straight to Phase 4's build — same
  error surface, one fewer round trip.
- **Ephemeral intermediates.** Materialize new intermediate models as
  ephemeral so they inline into the target at compile time. No separate
  warehouse round trip creates them as views.
- **Phase 3 writes only what the plan approved.** Budget scales with
  the plan's write set; no silent retries — two failed attempts on the
  same file = stop and ask.
- **One build for parity** (`build --model +<target>+ --target <non_prod>`),
  which also exercises downstream — do not do a target-only build followed
  by a full-project build. **Always on a non-prod target** to avoid
  writing an unverified refactor over the production relation.
- **Multiplicity-aware NULL-safe parity is the gate; aggregates and
  EXCEPT are not sufficient.** Aggregates (count/sum/min/max) miss value
  swaps between keys and non-numeric changes. Plain `EXCEPT` dedupes, so
  it misses row-multiplicity shifts (e.g. a fan-out that turns {A,A,B}
  into {A,B,B}). Use the row-count equality check PLUS the per-row-count
  `FULL OUTER JOIN ... ON a.c IS NOT DISTINCT FROM b.c` comparison from
  Phase 4 as the pass/fail signal — both must pass. `IS NOT DISTINCT
  FROM` is required so NULL-valued cells match NULL on the other side.
  Pass identifiers through from `manifest.json` verbatim — do not re-case
  or re-quote them.
- **Column-contract via `INFORMATION_SCHEMA.COLUMNS`, not `schema.yml`.**
  Do NOT fan out per-model `schema-verify` calls — `schema.yml` typically
  documents a curated subset of columns, so verify-against-yml produces
  false "mismatch" reports with high rate and low information. Use the
  explicit before/after `INFORMATION_SCHEMA.COLUMNS` diff in Phase 4 step 6
  instead; it compares the materialized relations directly, which is
  what Phase 3's column-preservation contract actually requires. `dbt
  build` on its own does NOT verify column name / order / type.
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
