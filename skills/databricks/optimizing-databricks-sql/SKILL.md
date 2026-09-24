---
name: optimizing-databricks-sql
description: Analyze DBSQL queries — including SQL embedded in notebooks (`spark.sql(...)`, `%sql` cells) — for anti-patterns, lint issues, and performance problems, using Databricks-specific dialect and platform knowledge (Delta, Photon, Unity Catalog) layered on top of altimate-code's generic SQL engine. Use when a user asks to optimize, review, or lint DBSQL queries on Databricks, whether standalone or embedded in a notebook. PySpark DataFrame-level analysis and cluster sizing are deferred to a later phase.
---

# Databricks Optimize (DBSQL)

A Databricks/Delta-platform **overlay**, not a standalone optimizer. The
generic rewrite/analyze/verify pipeline (Steps 1, 5, 6) is the same
pipeline altimate-code's native `query-optimize` skill runs — same tool
calls, same composition. This skill's only job is the part `query-optimize`
structurally can't do: detecting Databricks/Delta platform-specific issues
(Z-ordering, table statistics, Photon UDF blocking) that need table
metadata and Databricks docs knowledge, not just query text, and folding
those findings in alongside the generic ones.

If `query-optimize` is installed in the current environment, prefer
invoking it for Steps 1/5/6 and layer Steps 2–4's Databricks-specific
findings on top of its output, the same way `sql-review` defers to
sibling skills instead of duplicating them. If it isn't available (e.g.
this skill is running standalone, outside altimate-code), fall back to
calling the same tools directly as described below — the tool calls are
identical either way, so behavior doesn't change based on which path ran.

No rewrite is reported as "optimized" until it clears the validation gate
in Step 7 — that gate is a hard requirement, not a suggestion.

## When to use this skill

**Use when:**
- The query is DBSQL (standalone or embedded in a notebook cell) and the
  question involves Databricks/Delta-specific behavior: Z-ordering,
  liquid clustering, table statistics, Photon, Unity Catalog, Predictive
  Optimization.

**Do NOT use for:**
- Generic, dialect-agnostic SQL optimization with no Databricks-specific
  angle → use `query-optimize` directly.
- SQL quality/safety linting unrelated to performance (injection, PII
  exposure, style) → use `sql-review`.
- PySpark DataFrame-level code (`.collect()`, `.join()`, UDFs used as
  Python objects) → deferred to a later phase, out of scope for now.

## Before anything else — confirm the file path resolved correctly

**Confirm the resolved file path matches what was requested, before
doing anything else.** If the user gave an explicit path (a
`/Workspace/...` path, a repo path, any specific path), the tool used to
read or write it must resolve to *that exact path* — not a same-named
file found some other way. If the proper access tool fails, or the only
way to find something is a generic filename search, **stop and disclose
it explicitly** before analyzing or writing anything: state what path
was requested, what (if anything) was found instead and where, and ask
how to proceed. Never silently substitute a different file and continue
as if it's the same one.

**If no specific path was given at all** (a generic request naming no
file), a broader search — local files, a workspace listing — is a
reasonable way to find a match. But the report must still state which
path was actually used, so the reader can confirm it's the right one
rather than discovering it was wrong after the fact.

## Workflow

| Step | Action | Tool(s) | Detail |
|---|---|---|---|
| 0. Locate warehouse | Confirm a Databricks connection exists; get its name for later calls | `warehouse_list` | — |
| 1. Baseline | Run with `dialect: databricks`, plus the composite validate/lint/safety/PII pass | `sql_analyze`, `altimate_core_check` | via `query-optimize` if available; see below if parsing fails |
| 2. Platform overlay | Cross-check against Databricks/Delta patterns the generic engine structurally can't detect from query text alone | — | [references/dbsql-anti-patterns.md](references/dbsql-anti-patterns.md) |
| 3. Ground truth | If a warehouse connection exists, confirm claims against real table metadata before stating them as fact | `schema_inspect`, `sql_execute` (`DESCRIBE DETAIL`) | [references/delta-table-health.md](references/delta-table-health.md) |
| 4. Classify | Tag each finding predicate-level vs. strategy-level | `sql_explain` (`EXPLAIN FORMATTED`) | see below |
| 5. Rewrite | Generate and verify a fix | `altimate_core_rewrite` (`verify_equivalence: true`), `altimate_core_equivalence` for hand-authored fallbacks | see below, via `query-optimize` if available |
| 6. Grade | Present grade + findings, tagged by source | `altimate_core_grade` | via `query-optimize` if available |
| 7. Validate | Correctness + performance gate | — | [references/validation.md](references/validation.md) |
| 8. Apply | Write the rewrite back, only on explicit confirmation | file edit | see below |

### Step 1 — when the statement type can't be parsed

Confirmed twice in live testing: `sql_analyze`/`altimate_core_check` and
related tools (`altimate_core_validate`, `altimate_core_migration`)
cannot reliably parse DDL (`CREATE TABLE ...`) or `MERGE` statements —
either failing outright or returning nothing, sometimes inconsistently
across tools on the identical text. This is a real tool-coverage gap,
not a signal that the statement has no findings. When it happens, fall
back to live execution for grounding instead of treating the parse
failure as "nothing to report": run the statement (or `EXPLAIN`/
`DESCRIBE DETAIL` against it) directly via `sql_execute`, and reason from
what actually happens — a real parse/constraint error from the engine
itself (e.g. `NON_LAST_MATCHED_CLAUSE_OMIT_CONDITION`,
`[MANAGED_TABLE_FORMAT]`) is stronger, more specific evidence than any
static tool's silence would have been anyway.

### Step 3 — ground truth

When Step 0 found a live Databricks warehouse connection, don't call a
query expensive on text alone — confirm it. `schema_inspect` the
referenced tables (pass the warehouse name from Step 0), both to ground
table-health claims in real metadata and to build the `schema_context`
Step 5's rewrite/equivalence calls need for accurate table/column
resolution. For any Delta table involved, run `DESCRIBE DETAIL <table>`
via `sql_execute` to get real `sizeInBytes`/`numFiles`. Check statistics
proactively here, on every referenced table — don't wait to discover a
missing-stats finding as a side effect of running `EXPLAIN` in Step 4.
Full methodology, the stats cost ladder, and the `samples.*` gotcha are in
[references/delta-table-health.md](references/delta-table-health.md) —
read it before making any stats-related recommendation. Default to the
cheapest check that answers the actual question:
`ANALYZE TABLE ... COMPUTE STATISTICS NOSCAN` for size-only questions
(e.g. broadcast eligibility), escalating to `FOR COLUMNS` (targeted) or
`FOR ALL COLUMNS` only if genuinely needed. `ANALYZE TABLE` is a
recommend-only action — see the confirmation rule below.

### Step 4 — classify before deciding what to recommend

**Predicate-level** (function-wrapped filter, redundant cast, non-sargable
comparison — expressible as alternate literal SQL text): run
`EXPLAIN FORMATTED` on the original and check whether the plan's
`RequiredDataFilters`/`PushedFilters` already reflect the fixed form.
- If yes — the runtime already rewrote it (Photon has been observed doing
  this automatically for a `DATE(col)='X'` predicate) — still recommend
  the explicit rewrite, but justify it on standards/portability grounds
  (not guaranteed on other runtimes/engines, small recurring compile-time
  cost), not as a performance claim, since `EXPLAIN` showed no plan
  difference on this data.
- If no — the plan still shows the unaddressed non-sargable form — the
  rewrite has a real, plan-evidenced performance basis.

**Example — checking whether the runtime already rewrote the predicate:**

Original: `... WHERE DATE(order_ts) = '2024-01-01'`. Run
`EXPLAIN FORMATTED` on that exact text and read the scan node's
`PushedFilters`/`RequiredDataFilters`. (`DATE()` predicates are a tracked
rewrite-engine gap — see
[references/rewrite-engine-gaps.md](references/rewrite-engine-gaps.md)
#2 for how to actually produce the rewrite text; this example is about
which verdict the classification earns, not how to generate the fix.)

**Case A — plan already shows the range form:**
```
+- Relation sales.orders[...]
   PushedFilters: [order_ts >= 2024-01-01 00:00:00, order_ts < 2024-01-02 00:00:00]
```
Report it as: *"No measured gain on this engine — `EXPLAIN` shows an
identical plan either way. Recommended for portability: a different
engine, an older Databricks Runtime, or a Photon-disabled session isn't
guaranteed to constant-fold this the same way."* Step 7's verdict for
this one must be **Correct, not faster** — never **Optimized**.

**Case B — plan still shows the function-wrapped form:**
```
+- Relation sales.orders[...]
   PushedFilters: [isnotnull(order_ts)]
   -- DATE(order_ts) evaluated per-row in the Filter node above the scan
```
Same rewrite, different justification: the current plan evaluates
`DATE()` per row and can't push the predicate into file pruning. This one
can legitimately reach **Optimized** if Step 7's Tier 1/Tier 2 checks
confirm an actual measured or structural improvement.

**Why still rewrite it in Case A, if `EXPLAIN` shows no difference?**
Cases A and B produce the *same* recommended SQL text for *different*
reasons, and reporting the wrong reason is worse than reporting none.
Case A's rewrite is insurance against something this session can't
observe — a future migration or runtime change; Case B's is a fix for
something this session directly measured. Collapsing both into one
"this is bad, fix it" verdict would overstate Case A's evidence, and it's
exactly the kind of claim the Step 7 gate exists to catch — a rewrite
labeled "Optimized" with no `EXPLAIN`/`query.history` difference behind
it.

**Strategy-level** (join type, shuffle/`Exchange` placement, aggregation
approach, broadcast decision — a plan-level choice with no equivalent SQL
text): don't try to write literal SQL for this — there is none. Instead:
1. Check `EXPLAIN`'s `Optimizer Statistics` section first. A cost-based
   choice (e.g. not broadcasting a small table) is often just downstream
   of missing/stale statistics (see `dbsql-anti-patterns.md` #2b). If so,
   recommend `ANALYZE TABLE ... COMPUTE STATISTICS` — this lets the
   optimizer adapt as data changes, which is more robust than freezing
   today's decision. Recommend it; don't run it (confirmation rule below).
2. Only if stats are already current and the choice still looks wrong,
   consider a hint (e.g. `/*+ BROADCAST(t) */`) as an explicit override —
   flag it as forcing a decision rather than fixing a root cause, and note
   it needs revisiting if data volume changes (a hint doesn't adapt).

Every proposal from either path — tool-generated or hand-authored — still
goes through the Step 7 validation gate. Classification decides what's
worth proposing, not whether it needs verification.

### Step 5 — rewrite

1. Call `altimate_core_rewrite(sql, schema_context, verify_equivalence: true)`
   first, every time, regardless of past results — one call proposes a
   rewrite and proves it's semantically equivalent, partitioning results
   into verified-safe vs. review-before-applying.
2. If it returns nothing, check
   [references/rewrite-engine-gaps.md](references/rewrite-engine-gaps.md)
   for a matching known pattern and its documented workaround before
   hand-authoring from scratch — a known gap already has the specific
   trap and evidence-citation instructions worked out; don't re-derive
   them freehand.
3. If the finding doesn't match a tracked gap either, hand-author it
   grounded in what a tool actually showed this session (`EXPLAIN`,
   `DESCRIBE DETAIL`) — never from general SQL knowledge alone — then
   verify explicitly with `altimate_core_equivalence(sql1: original,
   sql2: candidate, schema_context)`, since there's no
   `altimate_core_rewrite` call to attach `verify_equivalence` to for a
   hand-authored candidate.

Every path — tool-generated or hand-authored, tracked gap or novel —
still goes through the Step 7 validation gate. An empty tool result
doesn't mean there's nothing to propose, and nothing here is exempt from
validation.

### Step 6 — grade

Present: grade, findings (tagged generic-engine / Databricks-specific
overlay / outside the defined pattern set — see below), and the verified
rewrite if one exists. If a query has nothing safe to rewrite (e.g. an
unfiltered `SELECT *` with no predicate to fix), say so — flag it, don't
force a rewrite that changes semantics just to have something to show.

**Beyond the defined pattern set.** `sql_analyze`'s full rule set,
`altimate_core_check`'s syntax/safety/PII pass, and
`dbsql-anti-patterns.md`'s catalog can all come back clean while
something genuinely wrong is still visible in evidence already gathered
in Step 3/4 (an `EXPLAIN` shape, a `DESCRIBE DETAIL` result, a
`query.history` pattern) that just doesn't match either catalog's
entries. Don't suppress that for lack of a matching rule — propose it,
held to the same bar as everything else in this skill:
- Ground it in an actual tool call made in this session — the "Don't
  assert, verify" rule below applies identically; novelty is not an
  exception to it.
- Tag it explicitly **outside the defined pattern set**, distinct from
  the generic-engine and Databricks-overlay tags, so the report doesn't
  borrow catalog-level confidence it hasn't earned.
- Route any resulting rewrite through Steps 5–7 exactly like a
  catalogued finding — hand-authored, evidence-cited, equivalence-
  verified, subject to the Step 7 validation gate. Being uncatalogued is
  not a shortcut past validation; if anything it's the opposite, since
  there's no matched rule or prior worked example backing the claim.

If genuinely nothing is found and nothing evidence-grounded suggests
itself either, that's the "nothing safe to rewrite" branch above — say
so plainly, don't manufacture a finding just to have something to report.

## Validation gate — nothing is "optimized" until this passes

Two independent, both-required checks, run via
[references/validation.md](references/validation.md):

1. **Correctness** — the rewrite's output matches the original's output.
2. **Performance** — the rewrite measurably runs faster than the original,
   by more than the noise observed across repeated runs, not just
   numerically lower once.

Step 5's equivalence check (`verify_equivalence: true`, or a follow-up
`altimate_core_equivalence` call for hand-authored fallbacks) checks
logical/semantic equivalence; this gate additionally checks the rewrite is
*actually* measurably faster against real execution — a different
question equivalence doesn't answer.
If either check fails, is inconclusive, or can't be run (no warehouse
connection), say so plainly — "semantically unverified," "no measured
improvement," "couldn't validate — here's why." Every claim about what the
engine did (a plan showing a rewrite, a table's size) must trace back to an
actual tool call made in this session, not general knowledge of how
Spark/Databricks usually behaves.

Correctness checks are not composed ad hoc: decide scope first (window vs.
full table — `validation.md` §Step 1, including the mandatory
data-availability check before windowing), then use the tool-call recipe
in `validation.md` §Step 2, not a freehand query. `data_diff` is reserved
for cross-platform migration validation or localizing an already-found
mismatch — see `validation.md` §Step 2 for why it isn't the default.
Never hand-type checksum SQL from memory or by reasoning about what the
logic "should" look like — follow the explicit tool-call recipe in
`validation.md` instead.

## Confirmation required: never auto-run `ANALYZE TABLE`

Every other command this skill runs is read-only (`SELECT`, `DESCRIBE`,
`EXPLAIN`, `SHOW STATISTICS`). `ANALYZE TABLE ... COMPUTE STATISTICS` is
different — it triggers a real scan (cost and time scaling with table
size) and writes new metadata. Recommending it is fine and expected;
running it without asking first is not, regardless of whether the session
is in an auto-approve/"yolo" mode that would normally skip confirmation for
other tool calls. State the recommendation and the exact command, then
wait for explicit go-ahead. Applies every time `ANALYZE TABLE` comes up —
Step 3's proactive stats check and Step 4's strategy-level findings alike.

## Applying the rewrite

Presenting a verified rewrite is not the same as shipping it. After the
report, if the rewrite's correctness was verified (verdict `Optimized` or
`Structurally optimized, timing pending` — never `Not verifiable`, and
never a candidate the equivalence check itself left as
review-before-applying), ask the user explicitly whether to apply it to
the source file or notebook cell. Only write the change after an
explicit yes — the same confirm-then-act pattern as `ANALYZE TABLE`
above, and for the same reason: a verified rewrite is safe to
*recommend* unconditionally, but writing to the user's file is not
something to do without asking, auto-approve session or not.

**The confirmation prompt itself must restate the verdict, not just
correctness.** Don't rely on the full report having appeared earlier in
the conversation — a user deciding right now whether to overwrite their
file needs the decision-relevant facts in front of them at the point of
decision: the verdict name (`Optimized` vs. `Structurally optimized,
timing pending` — these mean different things about how much performance
confidence exists), and the `Source:` if the rewrite was hand-authored
rather than tool-generated (a gap-workaround rewrite arguably deserves
more scrutiny before writing than a tool-verified one). "Correctness
verified" by itself is half of what Step 7 established, and presenting
only that half at the one moment a file is actually about to change is
worse than presenting it in the full report, not equivalent to it.

**Never report "File updated" without confirming the write actually
happened.** Confirmed live: a session reported *"File updated — the file
now reads: [new SQL]"* when the file was, in fact, unchanged — no write
tool was available for that file path, and the failure was never
checked. A different run, hitting the identical missing-capability gap,
correctly said so instead of asserting success. After attempting a
write, verify it — read the file back, or check the write tool's own
success/failure return, whichever is available — before claiming
anything changed. If there's no working write capability for this file
path at all, say that plainly (the way the second run did) rather than
describing a change that didn't happen. This is the same "don't assert,
verify" discipline as everywhere else in this skill, applied to the one
step whose entire job is confirming something real changed.

## Notebooks — extracting embedded DBSQL

A notebook cell containing `spark.sql("...")` or a `%sql` magic cell is
still DBSQL, in scope the same as a standalone saved query:

1. Parse the notebook for embedded SQL (`spark.sql("...")`, `%sql` cells).
2. Extract each one and route it through the full workflow above
   (Steps 1–7) — report it the same way, with the same validation gate.
3. Out of scope for this phase (deferred with the rest of PySpark work):
   the notebook's surrounding
   DataFrame/Python-API code — `.collect()`, UDFs as Python objects,
   `.join()`/`.groupBy()` calls, caching, broadcast hints. `sql_analyze`
   structurally can't see non-SQL-text code; analyzing it needs
   `pyspark-anti-patterns.md`, which is deferred. Extract and analyze the
   embedded SQL only.

## Reference files

| File | Contents | Read when |
|---|---|---|
| [references/dbsql-anti-patterns.md](references/dbsql-anti-patterns.md) | Databricks/Delta patterns the generic engine can't detect from query text alone | Every query, as the Step 2 overlay |
| [references/delta-table-health.md](references/delta-table-health.md) | CBO vs. Delta data-skipping statistics, the cost ladder, Predictive Optimization limits | Before any stats-related recommendation |
| [references/validation.md](references/validation.md) | Correctness recipe, performance tiers, the five valid verdicts | Every rewrite, before reporting it as optimized |
| [references/rewrite-engine-gaps.md](references/rewrite-engine-gaps.md) | Patterns lint catches but `altimate_core_rewrite` doesn't fix, with the specific workaround for each | Step 5, whenever `altimate_core_rewrite` returns nothing |

## Presenting the result

```
Databricks Optimize: <file_or_query_name>
==========================================

Summary: 2 Databricks-specific findings, 1 rewrite (baseline: 3 generic findings via query-optimize)

Findings: 2
  [MEDIUM] Z_ORDER_CANDIDATE — `event_date` filtered repeatedly per
           system.query.history, not the table's clustering key.
           -> Needs a clustering-key change; not run automatically.
  [LOW]    MISSING_STATS — `orders` shows Optimizer Statistics: missing.
           -> ANALYZE TABLE main.sales.orders COMPUTE STATISTICS
              (not run automatically — needs your confirmation).

Rewrite
  Before: WHERE DATE(order_ts) = '2024-01-01'
  After:  WHERE order_ts >= '2024-01-01' AND order_ts < '2024-01-02'
  Source: known gap — DATE() function elimination, see
          references/rewrite-engine-gaps.md #2 (altimate_core_rewrite
          returned nothing; hand-derived and verified below)
  Correctness: row_count 4,083,290 both sides, checksum
               8488063342080952646 both sides (exact match)
  Equivalence: VERIFIED (schema-backed, altimate_core_equivalence)

Validation: Structurally optimized, timing pending
  Tier 2 (EXPLAIN): PushedFilters now shows the range form — structural
                     improvement confirmed.
  Tier 1 (query.history): pending — lag on this workspace.

Consistency check: PASS — no tool result this session contradicts
                   another (e.g. a grade score disagreeing with a
                   query that already executed successfully)

Verdict: Apply the rewrite (verified)? Z-ordering and stats are
recommend-only — confirm before running ANALYZE TABLE.
```

The `Correctness:` line is not optional decoration — `validation.md`
requires the raw row-count/checksum values shown verbatim, not just
"VERIFIED" asserted. If validation was windowed rather than full-table
(`validation.md` §Step 1), state the window explicitly, e.g.
`Correctness: row_count 8,204 both sides, checksum ... both sides —
windowed to order_date 2026-08-01–2026-08-08, not full table`. A
windowed correctness claim and a full-table one are different-strength
claims; the report must say which one this is, not leave it implied. Any hand-authored rewrite needs a `Source:` line
disclosing why it wasn't tool-generated — whether it came from a tracked
gap (`Source: known gap — NOT IN→NOT EXISTS, see
references/rewrite-engine-gaps.md #1`) or matched no catalog or gap at
all (`Source: outside the defined pattern set — no catalog or tracked-gap
match, hand-authored and verified below`). The reader should always be
able to tell a tool-verified rewrite from a hand-authored one, and — for
a hand-authored one — whether it followed a documented recipe or was
composed from scratch. Never just a pass/fail verdict on its own.

`Consistency check:` is a standing field, not one that only appears when
there's a problem — state `PASS` when nothing conflicts. When a tool
result contradicts evidence already established this session (e.g.
`altimate_core_grade` scores syntax 0/100 on a query that already
executed successfully via `sql_execute`), report `FLAGGED` with the
specific contradiction named, not just the raw score — a grading tool's
bug shouldn't silently make it into the report as if it were a real
finding about the query.

**No raw tool-call syntax or internal step numbers in the report.**
`altimate_core_rewrite(verify_equivalence: true)`, `sql_analyze`, and
`"Classification (Step 4)"` are internal vocabulary for organizing this
skill's own instructions — not something a reader needs or asked for.
Describe what was checked and what it showed in plain language instead
(e.g. "verified automatically" rather than naming the tool call; "the
predicate is already pushed down" rather than "Case A per Step 4"). This
doesn't apply to `Source:`, `Tier 1`/`Tier 2`, `Consistency check:`, or
**the checksum formula used in the `Correctness:` line** — those disclose
*which kind of evidence* backs a claim, which is decision-relevant, not
implementation trivia; keep them exactly as specified above. Confirmed
live why this distinction matters: a report that dropped the formula
name reported the exact same wrong value (`SUM(hash(...))`'s known
overflow-prone result) as a prior run that *did* name it — without the
formula visible, that violation of `validation.md`'s mandatory
`BIT_XOR(xxhash64(...))` recipe becomes undetectable from the report
alone. State the checksum function by name every time, in plain language
if needed ("checksummed via the collision-resistant recipe in
`validation.md`") but never omit which one ran.

**Use markdown formatting directly in the report — don't wrap the whole
response in one code fence.** Bold, headers, bullet lists, and inline
code spans let the host UI render the report with real structure and
syntax highlighting; a report wrapped entirely in a single ` ``` ` block
renders as flat, unstyled text instead, no matter how well-organized the
content inside it is. Confirmed live: two reports from the same skill,
same session, rendered completely differently — one richly formatted,
one a plain gray block — purely because of this. Reserve actual code
fences for SQL snippets (`Before:`/`After:`), not the report around them.
For findings sections specifically, a compact table (columns like
Severity/Source/Finding) is easier to scan than a bullet list once there
are 3+ short findings — but don't force long, evidence-backed findings
(an `EXPLAIN` excerpt, a multi-sentence justification) into a table cell;
give those a one-line table summary and let the supporting detail follow
as a normal paragraph underneath.

## Known limitations

- For known gaps in `altimate_core_rewrite`'s coverage (patterns lint
  catches but the rewrite engine doesn't yet generate a fix for), see
  [references/rewrite-engine-gaps.md](references/rewrite-engine-gaps.md).
