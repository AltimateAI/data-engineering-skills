# Databricks/Delta-specific DBSQL anti-patterns

Patterns that sit outside a generic, dialect-agnostic SQL lint engine
because they require Databricks *platform* or *table metadata* context,
not just the query text. Use these as an overlay on top of `sql_analyze`'s
baseline output, not a replacement for it. Each entry notes the evidence
needed to actually confirm it — don't flag one from query text alone if
the required tool call hasn't been run.

## 1. Filter column would benefit from Z-ordering / liquid clustering
A query repeatedly filters on a high-selectivity column that isn't the
table's clustering key. Text-only detection is unreliable — needs:
- `DESCRIBE DETAIL` or `DESCRIBE HISTORY` to check current clustering
  columns.
- Ideally, `system.query.history` to confirm the column is filtered
  repeatedly, not just in this one query — a one-off filter doesn't
  justify reclustering a large table.

## 2. Small-file problem
A table has a high `numFiles`-to-`sizeInBytes` ratio (many small files),
which hurts scan performance independent of query quality. Needs
`DESCRIBE DETAIL` output — not visible from SQL text at all. If confirmed,
the fix is operational (`OPTIMIZE`), not a query rewrite.

## 2b. Missing/stale statistics
See [delta-table-health.md](delta-table-health.md) for the full picture.
Two different mechanisms are both called "statistics," and both go
through `ANALYZE TABLE`, just via different clauses:
- **CBO statistics** (row/column stats, used for join ordering and
  cardinality estimation) — `ANALYZE TABLE ... COMPUTE STATISTICS [NOSCAN
  | FOR COLUMNS ... | FOR ALL COLUMNS]`, with a cost ladder from cheapest
  to most expensive — see `delta-table-health.md` for the full ladder and
  when to use each tier.
- **Delta data-skipping statistics** (file-level min/max metadata used
  for file pruning) — `ANALYZE TABLE ... COMPUTE DELTA STATISTICS` (DBR
  14.3+), a separate command with a narrow backfill use case; don't
  confuse it with the CBO variant above.
Check proactively (Step 3 in `SKILL.md`), don't wait to discover it as a
byproduct of running a query's `EXPLAIN`. Before recommending manual
`ANALYZE`, check whether Predictive Optimization already covers the
table — see `delta-table-health.md` for why this check is misleading
specifically on `samples.*` tables (Delta Shares aren't PO-managed).
Recommend, don't execute — this scans the table; always get explicit
confirmation first, even in an auto-approve session.

## 3. UDF registered and used inside DBSQL
A SQL UDF or a Python UDF registered and called from SQL doesn't block
Photon outright — confirmed via live `EXPLAIN` across two independent
test runs: Photon actually executes the UDF natively (`PhotonScalarUDF`,
the plan reports "fully supported"). The real cost is structural: a
non-deterministic or optimizer-opaque UDF result can't be grouped in a
single pass, so the planner falls back to a two-phase aggregation with a
shuffle (`PhotonShuffleExchangeSink`/`Source`) where an equivalent
built-in expression (e.g. a `CASE WHEN` replicating simple UDF logic)
stays single-phase, no shuffle. Detectable from SQL text alone (look for
non-built-in function calls / `CREATE FUNCTION` usage) — this one is a
pure text-based rule; flag it directly, no live check needed. **Distinct
from `sql_analyze`'s generic `FUNCTION_IN_FILTER` rule** — that one flags
a *built-in* function wrapping a filter column (non-sargable, defeats
pruning/index use, e.g. `DATE(col) = 'X'`); this one flags a
*user-registered* UDF anywhere in the query forcing this
aggregation-shape cost. A query can trip either, both, or neither —
don't treat a `FUNCTION_IN_FILTER` finding as already covering this.

**A UDF can also break `altimate_core_equivalence` outright.** Confirmed
live: the equivalence check can error (not just return "not equivalent")
on a query referencing a fully-qualified catalog UDF it can't resolve.
When that happens, don't treat the rewrite as unverifiable — the Step 7
checksum recipe (`references/validation.md`) doesn't depend on the
equivalence engine understanding the UDF's semantics at all, since it
compares real execution results directly. A checksum match from that
recipe is sufficient correctness proof on its own here, not a fallback
of last resort.

## 4. `MERGE INTO` clause ordering / schema evolution risk
Confirmed via live execution: Databricks evaluates `WHEN MATCHED`
clauses in the order written, taking the *first* one whose condition is
satisfied — and only the *last* `WHEN MATCHED` (and only the last
`WHEN NOT MATCHED`) of a set may omit its condition entirely. This is
not a soft "worth a second look" risk — swapping a conditional clause
after an unconditional one of the same type doesn't just change
behavior, it's illegal and fails to parse
(`NON_LAST_MATCHED_CLAUSE_OMIT_CONDITION`). So an existing multi-branch
`MERGE` with a conditional clause already ordered before an unconditional
one of the same type is *already* in the only legal ordering — flag it
for the user to confirm the *intent* is right (does the conditional
branch's semantics still make sense for this data), not to suggest
reordering, which would just fail to parse. Separately, `mergeSchema`-
style auto schema evolution paired with `UPDATE SET *`/`INSERT *`
(resolves by column name, not position) is a latent schema-drift risk if
the source ever gains a column — advisory only, not currently broken if
the two sides' schemas match today (check via `DESCRIBE DETAIL` on both
tables).

## 4b. Small-table broadcast in a MERGE without confirmed size
Same broadcast-candidate caution as any small dimension table — this is
Databricks' own broadcast join optimizer choice, not a user-controlled
hint. Only worth flagging if `sql_explain` shows a shuffle join where a
`DESCRIBE DETAIL` size check would suggest broadcast should have applied.

## 5. `VACUUM` interacting with time-travel or CDC reads elsewhere
Not detectable from a single query in isolation — flag only if the
codebase context includes both a `VACUUM ... RETAIN n HOURS` (especially
below the default 168h) and a `VERSION AS OF` / `TIMESTAMP AS OF` / CDC
read elsewhere that could be invalidated by early cleanup.

## 6. Unnecessarily narrow file format or missing table properties
`CREATE TABLE` without `USING DELTA` (defaulting to a non-Delta format) on
what's clearly meant to be a managed analytical table. Text-checkable
directly from the DDL.

## Coverage

This list is a starting hypothesis set, not a validated, exhaustive rule
set — treat findings from it with the same evidence discipline as
everything else here, and expand it as new patterns get confirmed against
real production DBSQL queries.

Checked against altimate-code's documented generic catalog
(`docs/docs/data-engineering/tools/sql-tools.md`: `sql_analyze`'s 19
lint rules plus `sql_rewrite`'s 6 rewrite strategies) — zero overlap.
Every entry above needs table metadata (`DESCRIBE DETAIL`/`HISTORY`,
`system.query.history`) or Databricks platform behavior the generic,
query-text-only engine structurally can't see, which is the actual basis
for calling this an overlay rather than a duplicate. Re-check this when
either catalog changes — the "no overlap" claim is a snapshot, not a
standing guarantee.
