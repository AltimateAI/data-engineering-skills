# Prompting tips — getting these skills to fire

These skills only help if Claude decides to consult them on your task. We measured this directly across textbook dbt prompts (mart refactors, model creation, cross-DB migration, asana_source restructuring) and found a strong, **reproducible pattern in how you phrase the prompt** decides whether the skill fires on the first turn.

You don't have to do anything special. But if you find the plugin "not engaging," it's almost always one of the phrasing patterns below.

## TL;DR

| Prompt shape | Skill auto-fire rate | Why |
|---|---|---|
| Starts with an imperative verb ("Create…", "Refactor…", "Migrate…") | **5/5 trials** | Claude treats the prompt as task spec → consults Skills first |
| Starts with describing existing broken state ("The X model is incomplete. Right now it joins… It's missing… It's tagged as PII…") | **0/5 trials** | Claude treats the prompt as "go read the file" → opens the file directly, never consults Skills |
| Starts with context, then the ask ("Fivetran is updating their package, so I want to change it directly. Remove X…") | **1/5 trials** | Claude often spawns a sub-agent first, skipping the skill |

(Data: 5-prompt × 5-trial sweep on `claude-sonnet-4-6` with the `data-engineering-skills` plugin enabled, plain configuration, no system-prompt nudges.)

## How to rephrase

If the skill isn't engaging on a prompt of yours, try moving the verb to the front.

### Refactor case

**Doesn't fire reliably** (0/5):

> The mart_patient_360 model is incomplete. Right now it joins patients, encounters, diagnoses, medications, and lab_results but the SELECT is mostly empty — it's missing the patient_id primary key, has no aggregated metrics, and just exposes raw PII fields like SSN and phone number. I need you to build this out into a proper patient 360 view…

**Fires reliably** (5/5 after rephrasing):

> Refactor the `mart_patient_360` dbt model to add: patient_id primary key, total encounter count, unique diagnosis count, active medication count, most recent lab result date, days since last visit, and a high/medium/low patient risk tier. The current model joins patients, encounters, diagnoses, medications, and lab_results but the SELECT is mostly empty and exposes raw PII (SSN, phone) — fix the compliance issues you see.

Same information, different framing. The model now sees the task verb up front and consults the `dbt-skills:refactoring-dbt-models` skill before opening the file.

### Migration case

**Likely to spawn a sub-agent without consulting the skill:**

> Fivetran is updating their Asana package, so I want to change that package directly. Remove all of the models in the tmp folder and have the `stg_asana__[name].sql` models reference the source tables directly.

**Fires reliably:**

> Refactor the `stg_asana__*.sql` models to reference source tables directly. Remove all models in the `tmp` folder. (Context: Fivetran is updating their Asana package and I want to change it directly rather than wait for the next release.)

The imperative ("Refactor…") leads. The context becomes a trailing parenthetical instead of a setup paragraph.

## Phrasings that fire reliably

These openers consistently trigger skill auto-discovery:

- `"Create a model called X that aggregates Y by Z…"` → `dbt-skills:creating-dbt-models`
- `"Refactor X to add/remove/fix Y…"` → `dbt-skills:refactoring-dbt-models`
- `"Migrate the X stored procedures to dbt models with Y as target. Run cross-database validation."` → `altimate-code:altimate-code`
- `"Find the top N expensive queries from QUERY_HISTORY"` → `snowflake-skills:finding-expensive-queries`
- `"Profile the Snowflake query with query_id=X and explain the bottleneck"` → `snowflake-skills:optimizing-query-by-id`
- `"Test the X model — assert primary key uniqueness, not-null on created_at, and relationships to dim_customers"` → `dbt-skills:testing-dbt-models`

## What if I don't want to change my phrasing?

That's fair. The plugin can be made more aggressive about consulting its skills regardless of how you phrase the prompt — see the SessionStart hook approach in the project tracking issues. But until that ships, the above rephrasing is the cheapest reliable way to get the skill to engage.

## Source

This pattern was discovered through controlled experiments documented at:
[`AltimateAI/data-engineering-skills/.../discovery-analysis`](https://github.com/AltimateAI/data-engineering-skills) (linking once the experiment artifacts are upstreamed).
