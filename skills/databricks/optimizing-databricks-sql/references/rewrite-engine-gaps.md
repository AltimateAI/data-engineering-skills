# Rewrite-engine gaps

Patterns where `sql_analyze` (lint) correctly flags an issue, but
`altimate_core_rewrite` (the deterministic AST-transform engine) doesn't
generate a fix for it — confirmed by actually calling the tool, not
assumed. These aren't Databricks-specific; they're gaps in altimate-code's
generic rewrite engine, tracked here because this is where they were
found. Add a row whenever a new one turns up; don't fold the finding back
into `SKILL.md` prose.

Each row's Workaround column is the complete instruction — SKILL.md Step 5
covers the general hand-authoring/verification procedure and doesn't
repeat per-pattern detail; this file is where that detail lives.

| # | Pattern | altimate-code coverage today | Workaround |
|---|---|---|---|
| 1 | `NOT IN (subquery)` silently returns 0 rows when the subquery's column can be `NULL` | Lint: `NOT_IN_WITH_SUBQUERY` (`sql_analyze`) flags it. Rewrite: `altimate_core_rewrite` returns nothing — confirmed in testing. Untested hypothesis for why: the rewrite is only safe when the column is provably non-nullable, and `schema_context` carries types but not nullability, so the engine may be correctly declining to guess rather than failing outright — worth re-testing if `schema_context` ever gains a nullability field. | Hand-author `NOT EXISTS`. Before proposing it, confirm the subquery's compared column can't return `NULL` — look for an explicit `IS NOT NULL` guard already in the subquery's own `WHERE` clause. If no such guard exists, either add it as part of the rewrite or don't propose the rewrite at all — `NOT IN` and `NOT EXISTS` are not interchangeable without it. Cite the actual `EXPLAIN FORMATTED` plan shape as supporting evidence (`NOT IN` typically forces a `BroadcastNestedLoopJoin`; `NOT EXISTS` gets a hash/sort-merge anti-join) rather than composing the rewrite from general SQL knowledge alone. Verify with `altimate_core_equivalence` — there's no `altimate_core_rewrite` call to attach `verify_equivalence` to here. |
| 2 | `DATE(col) = 'X'` / other function-wrapped predicates don't get rewritten to a range predicate | Lint: `FUNCTION_IN_FILTER` (`sql_analyze`) flags it. Rewrite: `altimate_core_rewrite` has returned nothing in testing — despite `docs/docs/data-engineering/tools/sql-tools.md` documenting "Function elimination" as `sql_rewrite` strategy #3, with a worked example (`YEAR(col) = 2026` → range predicate) for the structurally identical pattern. Worth re-trying every session; report to Altimate as still-broken only after an actual failed attempt this session. | Check `EXPLAIN FORMATTED` on the original first — Photon has been observed constant-folding this automatically, in which case the plan already contains the literal range-predicate text in `RequiredDataFilters`/`PushedFilters`. If so, transcribe that text directly rather than hand-deriving it — it's the engine's own deterministic output. If the plan still shows the unrewritten form, hand-derive the range predicate (mind the upper-bound exclusivity and timezone handling). Either way, verify with `altimate_core_equivalence`. |
