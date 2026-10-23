---
name: snowflake-query-optimization
description: |
  End-to-end Snowflake query optimization in one pass. Use when optimizing a Snowflake query for:
  (1) User provides a Snowflake query_id (UUID) to tune or speed up
  (2) User points at a `.sql` file in the repo (optionally with a `:L10-L80` line range) and asks to optimize it
  (3) Task mentions "optimize this query", "make this faster", "tune this file", or "speed up query_id X"
  (4) A slow query that must be rewritten without changing its result set
  Fetches SQL, rewrites it, proves correctness with row-count + column-wise parity, and returns a report. Target wall time: <5 min.
---

# snowflake-query-optimization

**Input (one of)** → fetch SQL → optimize → parity-validate → report.

Delegates warehouse work to `altimate-code` when available; falls back
to direct Snowflake SQL otherwise. Does not reinvent query-profile parsing.

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
(360s). Per-phase caps (sum ≤ 300s):
Phase 1 ≤30s · Phase 2 ≤45s · Phase 3 ≤75s · Phase 4 ≤90s · Phase 5 ≤60s.
If a phase exceeds its budget, stop the extra work and move on — the
report is the deliverable, not an exhaustive audit.

## Inputs — pick ONE

1. **Repo path**: `path/to/file.sql` (optionally with `:L10-L80` line range)
2. **Snowflake `query_id`** (UUID)

If neither is given, ask the user once, then proceed.

## Workflow

### Phase 1 — Fetch the query (≤30s)

**Repo path:** use the Read tool with the line range (do NOT shell out
to `sed`; the project convention is Read / `cat`).

**query_id:**
```sql
SELECT query_text, warehouse_name, warehouse_size,
       total_elapsed_time/1000 AS seconds,
       bytes_scanned/1e9       AS gb_scanned,
       bytes_spilled_to_local_storage/1e9  AS gb_spill_local,
       bytes_spilled_to_remote_storage/1e9 AS gb_spill_remote,
       partitions_scanned, partitions_total, rows_produced
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_id = '<query_id>';
```

Fall back to `INFORMATION_SCHEMA.QUERY_HISTORY()` if `ACCOUNT_USAGE` is
not readable. Save the baseline metrics — the final report needs them.

### Phase 2 — Diagnose (≤45s)

If `altimate-code` is installed, prefer it:
```bash
if command -v altimate-code >/dev/null 2>&1; then
  altimate-code run "Diagnose Snowflake query_id <id>: fetch operator stats, flag no-pruning, spill, SELECT *, join explosion, repeated subquery, unnecessary ORDER BY. Return a short bullet list of actionable fixes only." \
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

### Phase 4 — Parity validation (≤90s) — MANDATORY HARD STOP

Prove the rewrite is semantically identical. Use the same per-column,
NULL-safe approach as `snowflake-dbt-model-refactoring` — not `HASH(*)`
(which is not a valid Snowflake expression; `HASH` requires explicit
arguments).

**Step 1 — enumerate the column list from the SELECT.** Parse the
original query's final projection to get the ordered list
`[col1, col2, ... colN]` with their aliases.

**Step 2 — row count + per-column signature:**
```sql
WITH original AS ( <original_query> ),
     optimized AS ( <optimized_query> ),
     orig_agg AS (
       SELECT COUNT(*) AS n,
              HASH_AGG(col1, col2, /* ...colN... */) AS sig
       FROM original
     ),
     opt_agg AS (
       SELECT COUNT(*) AS n,
              HASH_AGG(col1, col2, /* ...colN... */) AS sig
       FROM optimized
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
WITH original AS ( <original_query> ),
     optimized AS ( <optimized_query> ),
     orig_grouped AS (
       SELECT col1, col2, /* ...colN... */ COUNT(*) AS n
       FROM original
       GROUP BY col1, col2 /* ...colN... */
     ),
     opt_grouped AS (
       SELECT col1, col2, /* ...colN... */ COUNT(*) AS n
       FROM optimized
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
syntax). `diff_rows` must be **0** for parity to pass. Any non-zero
value means at least one distinct row has a different multiplicity
between original and optimized.

**Hard stop:** if either check fails (`parity_ok = FALSE` or
`diff_rows > 0`), discard the rewrite and report the divergence — do
not present an unsafe optimization.

If `altimate-code` is installed, prefer delegating this entire phase:
```bash
if command -v altimate-code >/dev/null 2>&1; then
  altimate-code run "Run data parity on Snowflake between these two SQL statements. Report row count delta, per-column aggregate signature, and multiplicity check. PASS/FAIL only.\n\nORIGINAL:\n<orig>\n\nOPTIMIZED:\n<opt>" \
    --yolo --output /tmp/parity.md --dir "$(pwd)"
fi
```

### Phase 5 — Measure + report (≤60s)

Run the optimized query with the **same warehouse size** as the baseline
(if a query_id was provided) and capture its post-run stats from
`QUERY_HISTORY` using the new query_id. For repo-only input, run both
original and optimized once and compare `total_elapsed_time`.

Return this report — nothing more:

```
# Snowflake Query Optimization Report

Source: <repo path | query_id>
Warehouse: <name> (<size>)

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

## Non-goals

- No schema changes, clustering key changes, or warehouse resizing.
- Do not run any `ALTER`, `CREATE`, or `DROP` statements. Read-only +
  one benchmark SELECT of the rewrite.
- Do not touch unrelated queries or files.

## Behavior contract

- Never present an optimization without a passing parity check.
- Never silently drop a semantic difference (`UNION` vs `UNION ALL`,
  `NULL`-handling, implicit casts) — flag it in the report.
- Never claim a performance improvement without re-measuring; estimates
  are not improvements.
