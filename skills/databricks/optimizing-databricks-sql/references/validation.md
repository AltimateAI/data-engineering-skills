# Validation methodology

Two independent questions, both required: is the output the same, and is
it actually faster. Passing one without the other is not a success —
report it as what it is ("correct but not faster" / "faster but
unverified correctness").

## DBSQL

### Step 1 — decide scope first, before choosing a mechanism

Scope (how much data to check) and mechanism (`data_diff` vs. the recipe
below) are separate decisions — settle scope before picking a mechanism.

**1a. Does the query already define its own date scope?** (e.g. a
`DATE(col) = '2016-02-14'` predicate under test) — if yes, use that scope
as-is and skip to Step 2.

**1b. If not, is there a usable date/timestamp column at all?** Check via
`DESCRIBE TABLE` (schema only — confirms the column exists and its type,
nothing about its data).

**1c. Null check — mandatory.** `DESCRIBE TABLE` does not catch this. Run:
```sql
SELECT COUNT(*) - COUNT(date_col) AS null_count FROM table
```
(`COUNT(col)` skips nulls by SQL definition, so the gap from `COUNT(*)` is
the null count.) Any `WHERE date_col >= X AND date_col < Y` filter
silently excludes NULL-dated rows under standard SQL three-valued logic —
no choice of window ever includes them. If `null_count` is non-trivial,
either skip windowing and validate the full table, or proceed but
explicitly report "N rows with NULL `<date_col>` were excluded from this
windowed pass" — a windowed match must not be reported as implying full
coverage when it doesn't have it.

**1d. Check actual data availability before picking a window** — never
assume "last N days relative to today" has any data at all. Run
`SELECT MIN(date_col), MAX(date_col) FROM table` first. `samples.nyctaxi.
trips`, a common test fixture, only contains data from January–March
2016 — "last 7 days relative to today" against it returns zero rows on
both sides, which doesn't error; it silently reports `COUNT = 0` matching
`COUNT = 0` as "identical," a false "verified" result that never actually
checked anything. Pick a window that overlaps the table's real date
range, not an arbitrary offset from today.

**1e. Size the window to the table, not a fixed number.** Start narrow
(e.g. 7 days within the real data range from 1d), check the row count
actually inside it, and widen (e.g. to 30 days) only if that's too small
to be a meaningful check for this table's volume. Wider = lower residual
risk from temporal data heterogeneity (a schema change, a backfill, a
different upstream source at some point) but more cost — there's no
universally-correct fixed number.

This windowing is a genuine cost-reduction mechanism, distinct from row
sampling (which doesn't save compute — the full query already has to run
before you can sample its result): a pushed-down date filter can reduce
bytes scanned via Delta file-skipping/partition pruning. For
aggregation-style queries (small output), just validate the full result
set — the incremental cost over one scan is negligible. Windowing matters
most for non-aggregated queries returning large row sets.

**If this ends in a windowed check rather than full-table, the report
must say so explicitly** — the window size and actual date range used
(e.g. "windowed to 2026-08-01 through 2026-08-08," not just "7 days").
A correctness claim scoped to a window is a weaker, different claim than
one scoped to the whole table, and "VERIFIED" alone doesn't tell the
reader which one they're getting. See `SKILL.md`'s `Correctness:` field
requirement — this is the same rule, applied at the point the scope
decision actually gets made.

### Step 2 — choose mechanism, now that scope is settled

**Default to the tool-call recipe below**, applied to whatever scope
Step 1 decided. It carries no demonstrated cost or accuracy disadvantage
against `data_diff` — both are rigorous checksums; `data_diff`'s
distinguishing edge is *localizing* a mismatch, not detecting one more
reliably — and the recipe avoids `data_diff`'s `extra_columns` gotcha and
its PII/PHI/PCI exposure risk in row-level mode.

**Reach for `data_diff` specifically when:**
- **Cross-platform migration validation** (the same logical table on two
  different systems — Postgres→Databricks, Snowflake→Databricks, etc.).
  `data_diff`'s `source_warehouse`/`target_warehouse` split is built for
  this; the recipe below uses `xxhash64()`/`BIT_XOR()` — Databricks-native
  SQL functions that don't exist elsewhere, so it's structurally incapable
  of spanning two platforms. If this becomes a real need, treat it as a
  distinct skill (cross-dialect type mapping, multi-system connections),
  not something folded into this one.
- **Localizing an already-found mismatch** from the recipe below, instead
  of writing a manual `EXCEPT`/`MINUS` query by hand.
- If used: **always pass `extra_columns` explicitly.** Column
  auto-discovery only applies when `source`/`target` are plain table
  names; every comparison here passes two SQL queries instead, and
  query-mode only compares `key_columns` unless `extra_columns` is listed.
  Omitting it produces a silent false "match" that never checked the
  columns that actually matter. And **default to `algorithm: "profile"`**
  (column-level statistics only, no row values leave the database)
  whenever there's any chance of regulated data — `data_diff` can print up
  to 5 sample diff rows directly into tool output, which become part of
  the conversation and are sent to the LLM provider. Fine for public
  sample data; not fine for real customer tables without care. This is a
  hard rule once this skill is pointed at anything beyond `samples.*`.
- `data_diff` has failed twice in prior testing (a VARCHAR-length bug, an
  unregistered warehouse) — a failure is itself worth surfacing/filing,
  not silently routed around.
- Note: `data_diff` isn't strictly full-table-only — it has a
  `where_clause` parameter (documented for excluding sensitive accounts)
  that could equally scope a date range. It just has no dedicated
  "window" shortcut distinct from that general mechanism.

**Never** write checksum SQL freehand, or choose which columns "matter" by
reading the SELECT clause instead of running the discovery step below.
Both have happened in traced sessions — `HASH()` used instead of
`xxhash64()`, a column silently dropped, redundant round trips. Always use
the explicit tool-call sequence below instead of composing checksum SQL
from memory.

### Correctness recipe: mandatory ordered tool calls, not a query written from memory

A strict two-step sequence, applied to whatever scope Step 1 decided
(windowed or full query — add the same `WHERE` clause to both the
original and rewritten query identically if windowing). Step 1's
*returned result* — not a reading of the SELECT clause — is what Step 2
must use.

**Step 1 — discover columns, don't assume them.** Run, via the SQL
execution tool actually available in this session:
```sql
SELECT * FROM (<query, ORDER BY stripped>) t LIMIT 0
```
Take the column names from the tool's returned result metadata. Do this
for both the original and rewritten query. If the two column lists don't
match by name, stop — that's a correctness failure on its own; report it,
don't proceed to a checksum.

**Step 2 — checksum using exactly those discovered columns**, in the same
order for both queries:
```sql
SELECT
  COUNT(*)                                       AS row_count,
  BIT_XOR(xxhash64(col_a, col_b, col_c))         AS checksum
FROM (
  <original or rewritten query, ORDER BY stripped>
) t
```
Run once for the original, once for the rewrite. Quote both raw returned
values verbatim in the report — the actual two numbers side by side, not
"checksums matched." A verdict without the numbers shown isn't verified,
it's asserted.

Notes:
- `BIT_XOR()` over `SUM()`: bounded, cannot overflow regardless of row
  count. `SUM()` hit a real `ARITHMETIC_OVERFLOW` at ~4M rows under
  Databricks' default ANSI mode. `BIT_XOR`'s own weakness — an even
  number of identical duplicate rows can cancel back to the same value —
  is why `COUNT(*)` is run alongside it, not dropped.
- `xxhash64()` over `hash()`: 64-bit, much lower collision probability,
  and it's a native Databricks SQL function (no UDF — a UDF here would
  itself block Photon, a separate anti-pattern this skill is supposed to
  be catching, not introducing).
- If both tables/queries can be affected by concurrent writes between the
  two runs, pin to the same data with Delta time travel:
  `... VERSION AS OF <n>` on the base tables in both queries, so a
  mismatch can only mean "the rewrite changed behavior," not "the data
  changed underneath us."

### If the checksums don't match

Don't just report "FAIL" — localize it. Run an `EXCEPT`/`MINUS` between
the two result sets (bounded with a `LIMIT` for cost) to surface a
handful of actually-differing rows, so the mismatch is debuggable rather
than a bare verdict.

### Performance: tiered fallback, in order

Mirrors the correctness check's preference order (`data_diff` → tool-call
sequence → never freehand): try each tier in order, only fall to the next
one if the current one genuinely isn't available, and state which tier
the final number actually came from.

**Skipping a tier for cost or time reasons is not the same as attempting
it and getting no signal — never report the two identically.** If Tier 1
is skipped rather than genuinely attempted (e.g. for budget reasons),
the verdict ceiling is whatever Tier 2 actually established — at most
"Structurally optimized, timing pending" — never "Optimized." Confirmed
as a real, recurring failure mode in live testing: a session skipped
Tier 1 "for budget" on an otherwise-identical query and still reported
"Optimized," while a separate run on the same query genuinely attempted
Tier 1, hit lag, and correctly reported the lesser verdict. Same
checksums, same query — the only difference was whether Tier 1 was
actually tried. State explicitly whether Tier 1 was attempted-and-lagged
versus skipped-outright; these are not interchangeable in the report.

**Tier 1 — `system.query.history` (preferred, when not lagging).**
1. Disable/bypass the SQL warehouse result cache for both runs —
   otherwise a rerun of either query can return instantly from cache and
   the timing comparison is meaningless.
2. Run each version 3+ times. Alternate which one runs first across
   trials (don't always run original-then-rewrite) to cancel out
   systematic warm-up bias.
3. Look up each run's `statement_id` in `system.query.history` for real
   `total_duration_ms` and `read_bytes`. `system.query.history` can lag
   ingestion by 10+ minutes; if a lookup comes back empty shortly after
   running, either check again in a later session or drop to Tier 2 now
   and note Tier 1 can be revisited later. **State explicitly how it was
   checked** — "ran N trials, looked up statement_ids, got back M rows"
   — not just the conclusion ("no timing data available"). A report that
   only states the conclusion is indistinguishable from one where Tier 1
   was never actually attempted, which defeats the entire point of
   distinguishing genuinely-attempted-and-lagged from skipped.
   **Cap the wait: one lookup, optionally one short wait (well under a
   minute) and a single re-check, then move on to Tier 2 if still
   empty.** "Genuinely attempted" means a real lookup happened, not an
   escalating retry loop — confirmed live: a session chained `sleep 20`
   → `sleep 40` → `sleep 60` across repeated lookups, burning two full
   minutes of pure waiting in a single run chasing a signal that
   `system.query.history` had already told it, on the first check, was
   lagging by 10+ minutes. A wait that short was never going to succeed;
   report "lagging, not yet available" and move to Tier 2 instead of
   retrying against a lag that's already known to be much longer than
   whatever's being waited out.
4. Report median (or trimmed mean) per version, plus the spread across
   trials — the spread tells you whether a given delta is signal or
   noise. Call it "faster" only if the rewrite's median beats the
   original's median by more than the observed run-to-run spread.

**Tier 2 — `EXPLAIN` plan comparison (immediate, no lag, structural not
timed).** Applies to both DBSQL and PySpark — a DataFrame compiles through
the same Catalyst/Photon plan as SQL, so this tier is shared. Literal
syntax differs, though:
```sql
-- DBSQL
EXPLAIN FORMATTED <query>
```
```python
# PySpark
df.explain(mode="formatted")
```
Run on both versions and compare the physical plans directly — no
dependency on query history, so it's available the instant the
query/code is written.

Mode to use, by purpose (default to `formatted`, not plain; use
`extended`/`cost`/`codegen` only for the narrower questions each answers):

- **Default: `mode="formatted"`.** Splits the physical plan into a
  numbered outline plus node details — easier to cite one specific node
  precisely than pulling a line out of denser plain text, which matters
  given the verbatim-quoting rule below. Covers join strategy
  (`SortMergeJoin` vs `BroadcastHashJoin`), shuffle (`Exchange` nodes),
  and file-scan pruning (`PushedFilters`/`DataFilters` — the
  physical-layer decision that actually determines real file-skipping on
  Delta; see the EXTENDED note below for why this is a different question
  from "did Catalyst logically combine the filters").
- **Don't treat operator presence as automatically a problem.** A
  `SortMergeJoin` or an `Exchange` showing up in the plan isn't inherently
  bad — sometimes it's the right choice for the data. Only flag it when
  there's a concrete reason to think a different plan would do less work
  (e.g. a small dimension table that should broadcast but isn't).
- **Photon check.** `FORMATTED` shows the `== Photon Explanation ==`
  section with an explicit message either way — including the positive
  case (e.g. `The query is fully supported by Photon.`), not only the
  negative one. Quote the actual message text verbatim — "fully
  supported," a named unsupported operation, or nothing at all if this
  Databricks Runtime version doesn't produce the section — and report
  exactly what it said, not an inference either direction. Compatibility
  and benefit are still different questions: a query being
  Photon-eligible doesn't mean Photon meaningfully speeds it up. Photon is
  built for larger workloads (Databricks cites >100GB as the range it
  targets); queries that run in under ~2 seconds may see no noticeable
  benefit from it regardless of eligibility. Don't treat "Photon-eligible"
  alone as a finding worth reporting without weighing whether the query's
  actual size/complexity makes that eligibility matter.
- **Optimizer Statistics section — version-gated.** Databricks Runtime
  16.0+ lists referenced tables' stats status (missing/partial/full)
  directly in `EXPLAIN` output — this is the CBO/cardinality statistics
  `SKILL.md` Step 3 and `delta-table-health.md` already cover (the
  CBO-vs-data-skipping distinction, the cost ladder, and the Predictive
  Optimization caveats before recommending `ANALYZE TABLE`); don't
  re-derive that reasoning here, this section is just where the evidence
  shows up. On an older runtime this section may not appear at all — its
  absence means "this feature doesn't exist here," not "stats are fine."
  One thing genuinely not covered in `delta-table-health.md`: Delta
  data-skipping coverage specifically is reported under a *different*
  surface entirely — "Query performance insights" (currently Private
  Preview), with its own Full/Partial/Unavailable/Unused labels and a
  `COVERAGE_PHOTON` insight — not this `EXPLAIN` section at all.
- **`mode="extended"` — narrow, specific use: verifying column
  pruning.** Use it to confirm Catalyst actually eliminated unused
  columns from a `SELECT *` (compare the Analyzed vs. Optimized Logical
  Plan sections) — a separate optimization question from anything
  FORMATTED answers. Don't reach for it as a general "more detail" mode:
  it won't show Photon status, join strategy, or real pushdown — those
  are physical-execution decisions that don't exist yet at the logical-
  plan stage EXTENDED's extra sections cover; they only appear in the
  physical plan, which `formatted` already includes in full.
- **`mode="cost"`** — use specifically to check whether missing/stale
  table statistics might be undermining the plan's row-count estimates.
  COST shows what Spark *thinks* the data looks like (e.g. estimated
  rows/size feeding a broadcast decision) — treat these as estimates, not
  measured reality; don't treat a reported `sizeInBytes` as proof of
  actual data size.
- **`mode="codegen"` — rare, last resort.** Shows generated whole-stage
  Java code. Use only when there's a specific, already-suspected
  CPU-bound or expression-heavy issue (complex nested expressions, a UDF,
  codegen fallback) — not by default. This only illuminates the
  **JVM-fallback** portion of a query — Photon-executed stages run native
  C++ code with no equivalent Java codegen to inspect — so CODEGEN is
  really "why is the non-Photon part of this query slow," most useful
  paired with a `Photon Explanation` finding, not a standalone check.

Look for concrete, citable differences between the two versions: fewer
scans of the same table, a join strategy changing (e.g. `LeftAnti`
replacing a scalar-subquery pattern), a shuffle or sort step
disappearing. Quote the actual plan text verbatim in the report — never
paraphrase or reason about what a plan "typically" looks like; a claim
about what appeared in a plan is only valid if it's grounded in the
actual returned plan text, not inferred. Report this tier's findings as
"structurally verified less work," not "faster" — it isn't a timing
measurement, only evidence that less work is planned.

**Tier 3 — labeled client-side timing (last resort only).** Wall-clock
time from just before to just after each tool call, across the same
alternating multi-trial structure as Tier 1. This includes
network/dispatch overhead the real metrics don't, so it's noisier — two
queries with identical real execution time can show different numbers
here for reasons unrelated to the query. Only use this if Tiers 1 and 2
are both genuinely unavailable (e.g. the rewrite doesn't change the plan
shape at all, so Tier 2 has nothing to compare), and always label it
explicitly as a rough, overhead-inclusive estimate — never present it
with the same confidence as a Tier 1 number.

If Tier 2 confirms a structural improvement but Tier 1 hasn't produced a
number yet (the common case when `query.history` is lagging), that's
**"Structurally optimized, timing pending,"** not "Correct, performance
pending" — the
two are not the same state and shouldn't share a label. Only when
*neither* tier produces a usable signal does "Correct, performance
pending" apply — and only after Tier 2 (no lag, almost no cost to try)
has actually been attempted, not just Tier 1.

## Truthful-feasibility rule

Not all code has a valid rewrite, and not every valid rewrite is
measurably faster. Both are legitimate, reportable outcomes — neither
should be disguised as a win.

**DDL-only recommendations don't route through this gate the same way.**
A schema/format fix on a table with no existing data (not yet created,
or nothing to diff against) has no query to performance-test and nothing
to checksum — none of the six verdicts below are built for that case.
Don't force one. Say plainly that Step 7's correctness/performance gate
doesn't apply here and why ("table not yet created, nothing to diff"),
then give the structural/capability rationale for the recommendation on
its own terms, separate from the query-verdict vocabulary.

For everything else, the final verdict must be one of the following, used
**verbatim, in full** — confirmed live, more than once: "Structurally
optimized" on its own (dropping ", timing pending") has shown up in
reports even when the underlying reasoning was correct. The two verdicts
mean different things; state the whole name every time, not a shortened
version of it:

- **Optimized**: correctness passed, performance improvement exceeds
  noise — a Tier 1 (measured, multi-trial) result, since "exceeds noise"
  is specifically a timing-and-spread comparison Tier 2 doesn't make.
- **Structurally optimized, timing pending**: correctness fully verified;
  Tier 2 (`EXPLAIN`) confirms less work is planned, with the specific
  plan difference cited (a scan/join/shuffle change, a pushed filter);
  Tier 1 hasn't produced a number yet (`query.history` lag, or not yet
  re-run). This is the expected common outcome when the plan changes and
  history lags — cite the plan evidence, don't round it up to
  "Optimized" before Tier 1 confirms it, and don't round it down to
  "Correct, performance pending" either, since that verdict specifically
  means *no* tier produced anything. Revisit once Tier 1 catches up.
- **Correct, not faster**: rewrite verified equivalent, no measurable
  gain — keep the original, note why (e.g. Photon/AQE already handled
  it). **This requires the plan to show no structural difference at
  all** (the Case A shape from Step 4 — `EXPLAIN` on both versions is
  the same). Confirmed as a real, live mix-up: don't default to this
  verdict just because Tier 1 didn't run — check Tier 2 first. If
  `EXPLAIN` shows *any* structural difference (fewer nodes, an
  eliminated shuffle stage, a changed join strategy), the floor is
  "Structurally optimized, timing pending" above, never "Correct, not
  faster" — those two verdicts are easy to conflate exactly when Tier 1
  is missing, and they mean opposite things about whether the rewrite
  does less work.
- **Not verifiable**: couldn't run the checks (no warehouse/cluster
  access, execution failed) — say what's missing, don't guess at a
  verdict.
- **No safe rewrite found**: flag the issue, don't force a change.
- **Correct, performance pending**: correctness fully verified via the
  mandatory tool-call sequence; performance was genuinely attempted
  across all applicable tiers (at minimum Tier 1 and Tier 2, since Tier 2
  has no lag and costs almost nothing to try) and **neither tier**
  produced a usable signal — not a logic failure, not skipped, not
  fabricated, and not the same state as "Structurally optimized, timing
  pending" above, which has a real Tier 2 signal behind it. This outcome
  should be rare — most sessions should get at least a structural
  (Tier 2) signal even when Tier 1 is lagging — so if it shows up
  repeatedly for the same environment, treat that as an environment
  problem worth investigating, not a normal resting state.
