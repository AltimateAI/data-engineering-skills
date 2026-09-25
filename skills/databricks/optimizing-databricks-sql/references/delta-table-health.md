# Delta table health — statistics, ANALYZE, and Predictive Optimization

Table/storage-layer health is a different concern from query-text
anti-patterns: a perfectly-written query can still be slow because the
underlying table has no statistics or is badly fragmented. That's a table
problem, not a SQL problem, and it needs different tools to check and
different commands to fix.

## Two statistics mechanisms

Both go through `ANALYZE TABLE`, but as different clauses — don't
conflate them, and don't recommend one when the other is what's needed.

**1. CBO statistics** (row/column stats used for join ordering and
cardinality estimation):
```sql
ANALYZE TABLE t COMPUTE STATISTICS NOSCAN              -- size only, no table scan, cheapest
ANALYZE TABLE t COMPUTE STATISTICS                     -- + row count
ANALYZE TABLE t COMPUTE STATISTICS FOR COLUMNS c1, c2  -- + per-column stats, targeted (only the join/filter columns the CBO actually uses)
ANALYZE TABLE t COMPUTE STATISTICS FOR ALL COLUMNS     -- + per-column stats, every column (most expensive)
```
Cost ladder, cheapest to most expensive: `NOSCAN` → bare → `FOR COLUMNS`
(targeted) → `FOR ALL COLUMNS`. Default to the cheapest tier that answers
the actual question — `NOSCAN` if only size matters (e.g. a
broadcast-eligibility check), `FOR COLUMNS` naming just the join/filter
columns involved in the query being analyzed, not `FOR ALL COLUMNS`
reflexively.

**2. Delta data-skipping statistics** (file-level min/max metadata used
for file pruning) — a separate command:
```sql
ANALYZE TABLE t COMPUTE DELTA STATISTICS   -- DBR 14.3+
```
This does NOT collect CBO stats — Databricks' docs state that normal
optimizer statistics are skipped when the `DELTA` keyword is given. Its
use case is narrow: recomputing data-skipping stats for existing rows
after changing which columns are configured for data skipping
(`delta.dataSkippingStatsColumns` or similar) — not something to run
routinely. Under normal operation, data-skipping stats are collected
automatically as new data is written; this command is a backfill/repair
tool for existing rows after a config change, not the default way these
stats get maintained.

## Predictive Optimization — narrower than "it's probably fine"

Predictive Optimization (PO) automatically runs `ANALYZE` on Unity
Catalog **managed** tables. Two real limits:
- **Background/threshold-based, not instant.** A "missing" result doesn't
  necessarily mean PO is disabled — it might just not have run yet.
- **Only applies to tables you actually manage.** A table accessed via
  Delta Sharing (anything under "Shares received" in the catalog browser)
  is NOT a Unity Catalog managed table in the consuming workspace — PO
  does not apply to it, and manual `ANALYZE` can't fix that either, since
  you don't own the table.

`samples.nyctaxi.trips` — commonly used as a test fixture — sits under
"Shares received," so `EXPLAIN` against it will show `missing` stats
regardless of anything recommended: PO structurally doesn't apply to a
shared table. Don't use a `samples.*` table to test whether an
`ANALYZE`/PO recommendation actually works — the `missing` result there
is a property of the table's sharing status, not a signal about the
recommendation logic. Use a table you own instead.

## Confirmation gate

Never auto-run any `ANALYZE TABLE` variant — recommend it, state the exact
command, and wait for explicit confirmation, even in an auto-approve
session (see `SKILL.md`'s confirmation-gate section, which this applies
under). This is the one mutating, scan-cost-bearing command in this
skill's whole workflow; everything else is read-only. Applies to all four
variants above equally — `NOSCAN` is cheap but still not free, and still
not a call to make unprompted.

## Not yet covered

`OPTIMIZE`, `ZORDER`, liquid clustering, and `VACUUM` retention tuning are
Delta table-health topics too — see `dbsql-anti-patterns.md` #1, #2, and
#5 for the parts currently covered.
