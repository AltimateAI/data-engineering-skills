# Skill Research & Evaluation

## Research Summary

### Key Pain Points Identified from Reddit & Community

1. **YAML Generation is Tedious** (frequently mentioned)
   - Creating sources.yml, staging models, and schema.yml manually is time-consuming
   - Tools like dbt-codegen help but require manual workflow

2. **Incremental Models are Complex** (common pain point)
   - Partition pruning issues
   - Unique key problems causing merge failures
   - Schema change handling
   - Full refresh vs incremental confusion
   - Idempotency challenges

3. **dbt Code Review Needs Structure** (process gap)
   - Teams lack checklists for PR reviews
   - Impact analysis before merging

4. **Snowflake Cost Attribution** (cost concern)
   - Finding expensive queries is only step 1
   - Need cost attribution by team/project
   - Warehouse sizing is confusing

5. **Data Quality is #1 Problem** (56% of analytics engineers)
   - Current testing skill covers adding tests
   - Missing: data quality monitoring, anomaly detection

### Existing Skills Analysis

| Skill | Coverage |
|-------|----------|
| creating-dbt-models | Model creation workflow, convention discovery |
| debugging-dbt-errors | Error fixing, 3-failure rule |
| testing-dbt-models | Schema tests, test patterns |
| documenting-dbt-models | YAML documentation |
| refactoring-dbt-models | Impact analysis, downstream deps |
| migrating-sql-to-dbt | Legacy SQL conversion |
| optimizing-query-text | Query optimization by text |
| optimizing-query-by-id | Query optimization by ID |
| finding-expensive-queries | Cost/performance analysis |

## Candidate Skills Evaluated

### Candidate 1: dbt Incremental Model Development
**Status: STRONG CANDIDATE**

**Why it's different:**
- Current `creating-dbt-models` skill focuses on general model creation
- Incremental models have unique workflow and gotchas not covered:
  - Choosing strategy (append, merge, delete+insert, insert_overwrite)
  - Partition pruning optimization
  - Late-arriving data handling
  - Schema change modes (append_new_columns, sync_all_columns)
  - Idempotency considerations
  - Unique key design

**Evidence of need:**
- Reddit/community discussions frequently cite incremental complexity
- dbt docs have extensive incremental content separate from regular models
- Common failure modes are incremental-specific

**Risk:** Could be seen as too narrow/specific

---

### Candidate 2: dbt Source/Staging Scaffolding
**Status: OVERLAP WITH EXISTING**

**Why it overlaps:**
- `creating-dbt-models` already covers convention discovery
- `documenting-dbt-models` covers YAML writing patterns
- The differentiation would be "initial setup" vs "ongoing development"

**Assessment:** Would add marginal value. The existing skills already guide users through convention discovery. REJECTED.

---

### Candidate 3: Snowflake Warehouse Configuration
**Status: ALREADY PLANNED IN ROADMAP**

The README explicitly mentions in roadmap:
> "Snowflake cost optimization (warehouse sizing, query patterns)"

**Assessment:** Should not duplicate planned work. DEFERRED.

---

### Candidate 4: dbt PR Review Checklist
**Status: TOO SUBJECTIVE**

**Why it's problematic:**
- Code review is highly context-dependent
- `refactoring-dbt-models` already covers impact analysis
- Would be difficult to make actionable without being too generic

**Assessment:** Better as documentation than a skill. REJECTED.

---

### Candidate 5: Data Quality Monitoring
**Status: ALREADY PLANNED IN ROADMAP**

The README mentions:
> "Data quality workflows (anomaly detection, freshness checks)"

**Assessment:** Should not duplicate planned work. DEFERRED.

---

## Decision

**Proceeding with:** dbt Incremental Model Development

**Rationale:**
1. Addresses a genuine gap - incremental models have unique workflows
2. High pain point from community research
3. Does not overlap significantly with existing skills
4. Not mentioned in roadmap (unlike cost optimization and data quality)
5. Can be tested and validated

## Testing Plan

1. Draft the skill
2. Simulate user scenarios to validate effectiveness
3. Compare behavior with vs without skill
4. Document results
5. Only add if demonstrably helpful

---

## Evaluation Results

### Skill: developing-incremental-models

**Differentiation Test (vs existing skills):**

| Existing Skill | What it covers | What it DOESN'T cover |
|----------------|----------------|----------------------|
| creating-dbt-models | General model creation, conventions | Incremental strategy selection, unique_key design |
| debugging-dbt-errors | General error fixing | Merge duplicate errors, partition pruning issues |
| testing-dbt-models | Adding schema tests | Incremental-specific test patterns |

**The incremental skill covers:**
- When to use incremental vs table (decision framework)
- Strategy selection (append, merge, delete+insert, insert_overwrite)
- unique_key design and verification
- Partition pruning optimization
- Late-arriving data handling
- Schema change modes
- Common failure patterns specific to incremental models

**None of these are covered by existing skills.**

**Quality Check:**
- [x] Actionable content with specific code patterns
- [x] Decision trees for strategy selection
- [x] Troubleshooting section for common failures
- [x] Clear anti-patterns
- [x] Testing checklist

**Risk Assessment:**
- LOW: Scope is focused and well-defined
- LOW: Trigger conditions are specific (mentions "incremental", strategies, etc.)
- LOW: Content is based on documented dbt best practices

### Final Decision

**ADD: developing-incremental-models**

Rationale:
1. Addresses genuine gap not covered by existing skills
2. High pain point from community research
3. Actionable content with specific guidance
4. Clear trigger conditions that won't conflict with other skills
5. Based on documented best practices

**DO NOT ADD (at this time):**
- Source/staging scaffolding - overlaps with existing skills
- PR review checklist - too subjective, better as documentation
- Warehouse sizing - already planned in roadmap
- Data quality monitoring - already planned in roadmap

**Recommendation:**
Add one skill (incremental models) and evaluate impact before adding more. Quality over quantity for an open-source repo.

---

## Summary of Changes

### Added

**1. developing-incremental-models** (`skills/dbt/developing-incremental-models/SKILL.md`)

A skill for creating and troubleshooting dbt incremental models.

**Key features:**
- Decision framework: when to use incremental vs table
- Strategy selection guide (append, merge, delete+insert, insert_overwrite)
- unique_key design and verification workflow
- Partition pruning optimization techniques
- Late-arriving data handling patterns
- Schema change configuration
- Common failure modes with specific fixes
- Testing checklist for incremental models

**Why this skill was added:**
1. Addresses a documented pain point (community research shows incremental models are a common source of confusion)
2. Provides genuinely different guidance from existing skills (none cover incremental-specific concerns)
3. High actionability (specific SQL patterns, decision trees, troubleshooting steps)
4. Clear trigger conditions that don't conflict with other skills

### Not Added (with reasons)

| Candidate | Reason for Rejection |
|-----------|---------------------|
| Source/staging scaffolding | Overlaps significantly with creating-dbt-models and documenting-dbt-models |
| dbt PR review checklist | Too subjective/context-dependent; refactoring skill already covers impact analysis |
| Snowflake warehouse sizing | Already planned in roadmap |
| Data quality monitoring | Already planned in roadmap |

### Files Changed

1. `skills/dbt/developing-incremental-models/SKILL.md` - NEW
2. `.claude-plugin/marketplace.json` - Added skill to dbt-skills plugin
3. `README.md` - Added skill to documentation
4. `docs/SKILL_RESEARCH.md` - This research document

---

## Research Sources

- [State of Analytics Engineering 2025](https://www.getdbt.com/blog/state-of-analytics-engineering-2025-summary) - dbt Labs
- [dbt Community Forum](https://discourse.getdbt.com/) - YAML generation discussions
- [Metaplane Blog](https://www.metaplane.dev/blog/10-ways-to-optimize-and-reduce-your-snowflake-spend) - Snowflake cost optimization
- [dbt Incremental Models Documentation](https://docs.getdbt.com/docs/build/incremental-models)
- [Orchestra dbt Best Practices](https://www.getorchestra.io/guides/data-build-tool-reddit---dbt-best-practices-community-insights)
- Reddit communities: r/dataengineering, r/analytics
