---
name: snowflake-query-optimization
description: |
  End-to-end Snowflake query optimization — fetch, rewrite, prove parity, benchmark, report. Use when:
  (1) User wants an **end-to-end flow** (fetch + rewrite + parity + benchmark + report), not just a rewrite
  (2) Input is a `.sql` file path in the repo (optionally `:L10-L80` line range), OR a Snowflake `query_id` (UUID)
  (3) User expects a correctness proof (row-count + per-column signature + multiplicity) before accepting the rewrite
  (4) Task says "optimize this query end-to-end", "tune this file and prove it's safe", "speed up query_id X with a parity check"
  **Prefer `optimizing-query-text`** for a pasted SQL string with no parity requirement (returns rewritten SQL only).
  **Prefer `optimizing-query-by-id`** for a quick profile-driven rewrite on a `query_id` with no parity re-run.
  Target wall time: ≤5 min (parity exempt — see Time budget).
---

# snowflake-query-optimization

**Input (one of)** → fetch SQL → optimize → parity-validate → benchmark → report.

Delegates warehouse work to `altimate-code` when available; falls back
to direct Snowflake SQL otherwise. Does not reinvent query-profile parsing.

## When NOT to use this skill

- Pasted SQL text, no parity needed → `optimizing-query-text`.
- Quick rewrite from a `query_id`, no re-run or parity → `optimizing-query-by-id`.
- Finding candidate queries to optimize → `finding-expensive-queries`.
- Refactoring a dbt model → `snowflake-dbt-model-refactoring`.

## Prerequisites

Before invoking, verify what's actually available — do **not** fabricate
results from file reads alone.

```bash
command -v altimate-code     # preferred delegate
command -v snowsql           # fallback client (any Snowflake client works)
```

Must have (one of):
- `altimate-code` installed and configured with a Snowflake connection, OR
- a working Snowflake client (`snowsql`, dbt adapter, Python with
  `snowflake-connector-python`, etc.) and credentials for the account.

Grants required on the Snowflake role:
- `SELECT` on `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` (preferred), or
  the ability to run `INFORMATION_SCHEMA.QUERY_HISTORY()` (fallback).
- `USAGE` on the warehouse referenced by the baseline query (needed to
  re-run it for comparison).

If neither path is available, stop and tell the user.

## Time budget

Target end-to-end runtime: **≤5 min** (300s), hard ceiling **6 min**
(360s), **excluding Phase 4 parity + Phase 5 benchmark re-runs**, which
scale with the baseline query's cost and are **exempt from the cap**.
A query being optimized is often slow by nature — forcing parity into
a 90s window would push the agent to skip the mandatory hard stop.

Per-phase caps (sum ≤ 300s, parity/benchmark separate):
Phase 1 ≤30s · Phase 2 ≤45s · Phase 3 ≤75s · Phase 4 overhead ≤60s (plus
re-run time) · Phase 5 overhead ≤30s (plus one re-run of the optimized
query). If a non-parity phase exceeds its budget, stop the extra work
and move on.

## Inputs — pick ONE

1. **Repo path**: `path/to/file.sql` (optionally with `:L10-L80` line range)
2. **Snowflake `query_id`** (UUID)

If neither is given, ask the user once, then proceed.

## Workflow

### Phase 1 — Fetch the query (≤30s)

**Repo path:** use the Read tool with the line range (do NOT shell out
to `sed`; the project convention is Read / `cat`). If the file is a dbt
model (contains `{{ ref() }}`, `{{ source() }}`, `{{ config() }}`, or
other Jinja), the raw text is NOT executable — run
`dbt compile --select <model>` first and read the compiled SQL from
`target/compiled/.../<model>.sql`. Only the compiled form can be sent
to Snowflake.

**query_id:**
```sql
SELECT query_type, query_text, warehouse_name, warehouse_size,
       total_elapsed_time/1000 AS seconds,
       bytes_scanned/1e9       AS gb_scanned,
       bytes_spilled_to_local_storage/1e9  AS gb_spill_local,
       bytes_spilled_to_remote_storage/1e9 AS gb_spill_remote,
       partitions_scanned, partitions_total, rows_produced,
       start_time
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_id = '<query_id>';
```

**Fallback for recent baselines:** `ACCOUNT_USAGE.QUERY_HISTORY` lags up
to ~45 min, so a `query_id` from the last 45 min may return zero rows.
If the row count is zero (not just "not readable"), fall back to:
```sql
-- Scope to the user, not the current session — the baseline query_id
-- was almost certainly run in a different session.
SELECT * FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(
  USER_NAME => CURRENT_USER(),
  END_TIME_RANGE_START => DATEADD(hour, -2, CURRENT_TIMESTAMP()),
  RESULT_LIMIT => 1000
))
WHERE query_id = '<query_id>';
```
If the baseline was run by another user, use
`INFORMATION_SCHEMA.QUERY_HISTORY(END_TIME_RANGE_START => ..., RESULT_LIMIT => ...)`
with the account-wide scope (requires the warehouse monitor privilege).
Do NOT use `QUERY_HISTORY_BY_SESSION()` for a baseline fetched by
`query_id` — it only returns the current session's queries, and the
baseline is almost always from a different session.

**Single-session requirement for Phases 4 + 5.** The temp tables created
in Phase 4 and the `ALTER SESSION SET USE_CACHED_RESULT = FALSE` setting
are session-scoped. All of Phase 4 (parity) and Phase 5 (benchmark)
must run in **one connected Snowflake session** — not separate
`snowsql -q` invocations or separate altimate-code calls.

If the only available client is per-call (one shell per statement), use
`scripts/parity_bench.sh`:

```bash
export SNOWFLAKE_RUN_SQL='snowsql -c myconn'   # or an altimate-code wrapper
export SQO_DEV_SCHEMA='DEV_<USER>'             # NEVER a shared schema (see below)
scripts/parity_bench.sh /tmp/sqo-orig.sql /tmp/sqo-opt.sql
```

The script addresses three failures the previous "SET parity_orig = ..."
form had:

- **Shell-generated `RUN_ID`.** The old form used `SET parity_orig =
  '_SQO_ORIG_' || UUID_STRING()` on session 1 and `DROP TABLE
  IDENTIFIER($parity_orig)` on session 2 — the session variable didn't
  survive, the DROP failed with "session variable does not exist", and
  the PII-bearing transient tables leaked indefinitely. The script
  generates `RUN_ID` in the shell (`uuidgen | tr -d -`), builds the
  table names as literals (`_SQO_ORIG_${RUN_ID}`), and the DROPs always
  know the full name.
- **Mandatory cleanup via `trap`.** `trap cleanup EXIT INT TERM` runs
  the DROPs on success, failure, Ctrl-C, or SIGTERM — nothing short of
  a kernel panic leaves the tables behind.
- **User dev schema only.** `SQO_DEV_SCHEMA` is REQUIRED (fail-closed).
  Writing parity tables to a shared schema would expose both result
  sets — potentially containing PII — to anyone with `USAGE` on it,
  until the next cleanup pass.

**MANDATORY HARD STOP — safety guard against DML/DDL re-execution.**
This skill re-executes the fetched SQL during parity (Phase 4) and
benchmark (Phase 5). Re-running a non-SELECT would mutate the warehouse.

- If input was a `query_id`: require `query_type = 'SELECT'`. If it is
  `INSERT`, `UPDATE`, `MERGE`, `DELETE`, `CREATE_TABLE_AS_SELECT`,
  `COPY`, `CALL`, or any other mutating type, **stop and tell the user**:
  this skill will not re-execute DML/DDL from history.
- If input was a repo path: inspect the fetched SQL. If the leading
  statement is not `SELECT` / `WITH ... SELECT`, stop with the same
  message.

Save the baseline metrics — the final report needs them.

### Phase 2 — Diagnose (≤45s)

If `altimate-code` is installed, prefer it. Pass the SQL via a temp
file (not a shell-interpolated string — SQL can contain `"`, `$`,
backticks, and Snowflake quoted identifiers like `"Order Id"` that
break double-quoted shell strings):

```bash
if command -v altimate-code >/dev/null 2>&1; then
  cat > /tmp/sqo-prompt.txt <<'EOF'
Diagnose Snowflake query_id <id>: fetch operator stats, flag no-pruning,
spill, SELECT *, join explosion, repeated subquery, unnecessary ORDER
BY. Return a short bullet list of actionable fixes only.
EOF
  altimate-code run "$(cat /tmp/sqo-prompt.txt)" \
    --yolo --output /tmp/diagnose.md --dir "$(pwd)"
fi
```
Then Read `/tmp/diagnose.md`.

Otherwise, pull operator stats directly:
```sql
SELECT * FROM TABLE(GET_QUERY_OPERATOR_STATS('<query_id>'));
```

Scan for these fixable issues only (ignore everything else):

| Signal | Fix |
|---|---|
| `partitions_scanned == partitions_total` | Add filter on a cluster key |
| `gb_spill_* > 0` | Reduce intermediate size (project early, filter early) |
| TableScan with `SELECT *` | Project only used columns |
| Join row explosion (output >> input) | Add join predicate / pre-filter |
| Repeated subquery | Fold into a CTE |
| `ORDER BY` without `LIMIT` in a non-final context | Drop it |

Repo-only input (no profile available): rely on the static patterns above.

### Phase 3 — Rewrite (≤75s)

Rewrite the query applying only the fixes identified. Semantic rules:

- Same SELECT list order, same column aliases, same row grain.
- Do not add or remove `LIMIT`.
- Do not change `UNION` to `UNION ALL` (dedup semantics differ).
- Keep `ORDER BY` in the outermost SELECT if the original had one there.
- Prefer CTEs over inline subqueries for readability.
- Keep comments and formatting consistent with the source file.

If a change would alter the result set, **skip it** and note why.

### Phase 4 — Parity validation — MANDATORY HARD STOP

Prove the rewrite is semantically identical. Use the same per-column,
NULL-safe approach as `snowflake-dbt-model-refactoring` — not `HASH(*)`
(which is not a valid Snowflake expression; `HASH` requires explicit
arguments).

**Disable result cache for honest comparisons** (one session setting
covers Phases 4 + 5):
```sql
ALTER SESSION SET USE_CACHED_RESULT = FALSE;
```

**Materialize once per side to avoid re-running the slow baseline
multiple times.** Signature and multiplicity both scan the same rows,
so land each result into a session-scoped temp table and compute both
checks over the temp tables:

```sql
CREATE TEMPORARY TABLE _sqo_orig_<run_id> AS <original_query>;
CREATE TEMPORARY TABLE _sqo_opt_<run_id>  AS <optimized_query>;
```

`<run_id>` is a timestamp or random suffix to avoid session-level
collisions. Temp tables are session-scoped and auto-cleaned at session
end — no explicit DROP needed.

**Step 1 — enumerate the column list from the SELECT.** Parse the
original query's final projection to get the ordered list
`[col1, col2, ... colN]` with their aliases.

**Step 2 — row count + per-column signature (one query, both sides):**
```sql
WITH orig_agg AS (
  SELECT COUNT(*) AS n,
         HASH_AGG(col1, col2, /* ...colN... */) AS sig
  FROM _sqo_orig_<run_id>
),
opt_agg AS (
  SELECT COUNT(*) AS n,
         HASH_AGG(col1, col2, /* ...colN... */) AS sig
  FROM _sqo_opt_<run_id>
)
SELECT o.n AS orig_rows, p.n AS opt_rows,
       o.sig AS orig_sig, p.sig AS opt_sig,
       (o.n = p.n AND o.sig = p.sig) AS parity_ok
FROM orig_agg o, opt_agg p;
```

`HASH_AGG` is an order-independent, multiset-aware aggregate on the
expanded column list — this catches duplicate-row cases that a
plain `HASH(... ,...)` would miss and is NULL-safe per-column.

**Step 3 — multiplicity sanity check** (catches the `{A,B}` vs
`{A,B,B}` case which can collide if two aggregates coincidentally
match). Group each side by every column to get per-distinct-row counts,
then full-outer-join the grouped sets and flag any row whose counts
differ or that only exists on one side:
```sql
WITH orig_grouped AS (
  SELECT col1, col2, /* ...colN... */ COUNT(*) AS n
  FROM _sqo_orig_<run_id>
  GROUP BY col1, col2 /* ...colN... */
),
opt_grouped AS (
  SELECT col1, col2, /* ...colN... */ COUNT(*) AS n
  FROM _sqo_opt_<run_id>
  GROUP BY col1, col2 /* ...colN... */
)
SELECT COUNT(*) AS diff_rows
FROM orig_grouped o
FULL OUTER JOIN opt_grouped p
  ON o.col1 IS NOT DISTINCT FROM p.col1
 AND o.col2 IS NOT DISTINCT FROM p.col2
 /* ...one line per column... */
WHERE COALESCE(o.n, 0) <> COALESCE(p.n, 0);
```
`IS NOT DISTINCT FROM` treats `NULL = NULL` as true (confirmed Snowflake
syntax). `diff_rows` must be **0** for parity to pass.

**Hard stop:** if either check fails (`parity_ok = FALSE` or
`diff_rows > 0`), discard the rewrite and report the divergence — do
not present an unsafe optimization.

If `altimate-code` is installed, prefer delegating this entire phase.
**Never shell-interpolate the SQL** — the baseline comes from
`QUERY_HISTORY` and may contain `$(...)`, backticks, or quoted
identifiers like `"Order Id"` that break the command or execute under
`--yolo`. Write both SQL files with the **Write tool** (not `printf`,
not `echo`), then reference the file paths in the prompt:

1. Use Claude Code's `Write` tool to create `/tmp/sqo-orig.sql`
   containing the original SQL verbatim.
2. Use the `Write` tool to create `/tmp/sqo-opt.sql` containing the
   optimized SQL verbatim.
3. Then invoke altimate-code with a prompt (also written via `Write` or
   a quoted heredoc) that references the files:

```bash
if command -v altimate-code >/dev/null 2>&1; then
  # Files /tmp/sqo-orig.sql and /tmp/sqo-opt.sql must already exist,
  # written via the Write tool (not shell).
  cat > /tmp/sqo-parity-prompt.txt <<'EOF'
Run data parity on Snowflake between the two SQL statements in
/tmp/sqo-orig.sql and /tmp/sqo-opt.sql. Set USE_CACHED_RESULT=FALSE
first. Materialize each into a temp table, then report row count delta,
per-column HASH_AGG signature, and GROUP-BY multiplicity. PASS/FAIL only.
EOF
  altimate-code run "$(cat /tmp/sqo-parity-prompt.txt)" \
    --yolo --output /tmp/parity.md --dir "$(pwd)"
fi
```

If a Write tool is not available (pure-shell execution context), use a
**quoted heredoc** — the single-quoted `'EOF'` prevents expansion:
```bash
cat > /tmp/sqo-orig.sql <<'EOF'
-- paste SQL between these fences, verbatim; the single-quoted EOF
-- prevents any $(...) / backtick / variable expansion
EOF
```
Never `printf '%s' "$sql" > file` or `echo "$sql" > file`.

### Phase 5 — Measure + report

Benchmarks are cache-sensitive. The session already has
`USE_CACHED_RESULT = FALSE` from Phase 4. For the clearest signal:
```sql
ALTER SESSION SET USE_CACHED_RESULT = FALSE;
-- Benchmark run (one execution of the optimized query):
<optimized_query>;
-- Capture the just-run query_id:
SELECT LAST_QUERY_ID() AS new_qid;
```

**Pull post-run stats from `INFORMATION_SCHEMA`, not `ACCOUNT_USAGE`**
(ACCOUNT_USAGE lags up to ~45 min and will return zero rows within the
60s report window):
```sql
SELECT total_elapsed_time/1000 AS seconds,
       bytes_scanned/1e9 AS gb_scanned,
       bytes_spilled_to_local_storage/1e9  AS gb_spill_local,
       bytes_spilled_to_remote_storage/1e9 AS gb_spill_remote,
       partitions_scanned, partitions_total
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION())
WHERE query_id = '<new_qid>';
```

If `ACCOUNT_USAGE` was used in Phase 1 for the baseline, that's fine
(the baseline is old enough to have landed there). Only the fresh
re-run must come from `INFORMATION_SCHEMA`.

**Note on repo-only input:** without a prior `query_id`, "before" and
"after" come from running both queries once each in this session.
Honestly label the baseline column as "this-session only" — Phase 4's
materialization already warmed local disk cache for the second run, so
large speedup claims (>5x) on identical warehouse state should be
flagged as "cache-adjacent" in the report.

Return this report — nothing more:

```
# Snowflake Query Optimization Report

Source: <repo path | query_id>
Warehouse: <name> (<size>)
Cache: USE_CACHED_RESULT=FALSE (verified)

## Parity
Row count:    <orig> → <opt>  (match: YES/NO)
Signature:    <orig_sig> → <opt_sig>  (match: YES/NO)
Multiplicity: <diff_rows> rows differ (pass: diff_rows=0)

## Performance (before → after)
Elapsed:          <s> → <s>  (-X%)
GB scanned:       <g> → <g>  (-X%)
Partitions:       <p>/<t> → <p>/<t>
Spill (local):    <g> → <g>
Spill (remote):   <g> → <g>
Stats source:     INFORMATION_SCHEMA (fresh)  |  ACCOUNT_USAGE (historical)

## Changes applied
- <bullet 1 — e.g. "Replaced SELECT * with 7 used columns">
- <bullet 2>
- <bullet 3>

## Optimized SQL
<fenced SQL>
```

If parity failed, replace Performance + Changes with:
```
## Parity FAILED — rewrite discarded
Divergence: <row count diff | signature diff | multiplicity diff>
Suspected cause: <brief>
```

## Anti-patterns (never apply)

- Change `UNION` → `UNION ALL`.
- Add or remove `LIMIT`.
- Rename columns or reorder the SELECT list.
- Convert `NOT IN` → `NOT EXISTS` without proving the subquery column is
  NOT NULL.
- Rewrite correlated subqueries as uncorrelated — semantics differ.
- Edit the repo file during this skill. Present the SQL in the report;
  only edit if the user asks afterwards.
- Interpolate raw SQL or user-supplied text into double-quoted shell
  strings. **This includes `printf '%s' "$sql" > file` and
  `echo "$sql" > file` — both expand the string before writing.** Use
  the `Write` tool or a **single-quoted heredoc** (`<<'EOF'`) only.
  Query text in `QUERY_HISTORY` was authored by other users and can
  contain `$(...)` or backticks that execute under `--yolo`.
- Re-run a non-SELECT fetched from history. Phase 1 guards this.
- Read the fresh re-run's stats from `ACCOUNT_USAGE` — it lags ~45 min.

## Non-goals

- No schema changes, clustering key changes, or warehouse resizing.
- No DDL beyond parity scratch tables. In the preferred single-session
  path those are `CREATE TEMPORARY TABLE` (auto-cleaned at session end).
  In the per-call fallback they are `CREATE OR REPLACE TRANSIENT TABLE`
  in the **user's own dev schema** (not a shared schema) and MUST be
  dropped on every exit path (success, parity FAIL, Ctrl-C).
- Do not touch unrelated queries or files.

## Behavior contract

- Never present an optimization without a passing parity check.
- Never silently drop a semantic difference (`UNION` vs `UNION ALL`,
  `NULL`-handling, implicit casts) — flag it in the report.
- Never claim a performance improvement without re-measuring; estimates
  are not improvements.
- Never re-execute DML/DDL from query history — Phase 1 hard-stops.
- Never interpolate SQL or user text into shell commands; always use
  temp files or heredocs.
- Never leave parity scratch tables (`_SQO_ORIG_*`, `_SQO_OPT_*`) behind
  — the full result sets of the original and optimised queries may
  contain PII or sensitive data. Mandatory DROP on every exit path.
- Never materialise parity tables into a shared schema when a user dev
  schema is available.
