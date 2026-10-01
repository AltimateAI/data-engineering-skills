# Airflow skill trigger eval: final-triggers-2026-10-01

- Models: claude-sonnet-5-5, claude-opus-5-5, claude-fable-5-1; runs per query: 2; max turns: 4
- Queries: 30 (18 should-fire, 12 near-miss); skill arm (repo skills + skills/airflow)
- skills/airflow sha256: `d3af9fac9ff0337042ffb634539cd96828c2f63020d1651fee7fe70fd09557a0`
- Spent: $40.10 of $150.00 cap

Recall = should-fire runs where the expected skill fired. Precision = runs where the skill fired that expected it. Confusion = the skill's own should-fire runs where a different Airflow skill fired. Near-miss false-fire = near-miss runs where the skill fired.

## All models

| Skill | Recall | Precision | Confusion | Near-miss false-fire |
|---|---|---|---|---|
| authoring-airflow-dags | 31/36 (86%) | 100% (31 fired) | 0/36 (0%) | 0/72 (0%) |
| migrating-to-airflow-3 | 36/36 (100%) | 100% (36 fired) | 0/36 (0%) | 0/72 (0%) |
| testing-airflow-dags | 35/36 (97%) | 100% (35 fired) | 0/36 (0%) | 0/72 (0%) |

Any Airflow skill on near-misses: 0/72 (0%). Outcomes: {"hit": 102, "miss": 6, "quiet": 72}.

## claude-sonnet-5-5

| Skill | Recall | Precision | Confusion | Near-miss false-fire |
|---|---|---|---|---|
| authoring-airflow-dags | 7/12 (58%) | 100% (7 fired) | 0/12 (0%) | 0/24 (0%) |
| migrating-to-airflow-3 | 12/12 (100%) | 100% (12 fired) | 0/12 (0%) | 0/24 (0%) |
| testing-airflow-dags | 11/12 (92%) | 100% (11 fired) | 0/12 (0%) | 0/24 (0%) |

Any Airflow skill on near-misses: 0/24 (0%). Outcomes: {"hit": 30, "miss": 6, "quiet": 24}.

## claude-opus-5-5

| Skill | Recall | Precision | Confusion | Near-miss false-fire |
|---|---|---|---|---|
| authoring-airflow-dags | 12/12 (100%) | 100% (12 fired) | 0/12 (0%) | 0/24 (0%) |
| migrating-to-airflow-3 | 12/12 (100%) | 100% (12 fired) | 0/12 (0%) | 0/24 (0%) |
| testing-airflow-dags | 12/12 (100%) | 100% (12 fired) | 0/12 (0%) | 0/24 (0%) |

Any Airflow skill on near-misses: 0/24 (0%). Outcomes: {"hit": 36, "quiet": 24}.

## claude-fable-5-1

| Skill | Recall | Precision | Confusion | Near-miss false-fire |
|---|---|---|---|---|
| authoring-airflow-dags | 12/12 (100%) | 100% (12 fired) | 0/12 (0%) | 0/24 (0%) |
| migrating-to-airflow-3 | 12/12 (100%) | 100% (12 fired) | 0/12 (0%) | 0/24 (0%) |
| testing-airflow-dags | 12/12 (100%) | 100% (12 fired) | 0/12 (0%) | 0/24 (0%) |

Any Airflow skill on near-misses: 0/24 (0%). Outcomes: {"hit": 36, "quiet": 24}.

## Confusion matrix (all models, runs)

| expected \ fired | authoring-airflow-dags | migrating-to-airflow-3 | testing-airflow-dags | (no airflow skill) | runs |
|---|---|---|---|---|---|
| authoring-airflow-dags | 31 | 0 | 0 | 5 | 36 |
| migrating-to-airflow-3 | 0 | 36 | 0 | 0 | 36 |
| testing-airflow-dags | 0 | 0 | 35 | 1 | 36 |
| near-miss (none) | 0 | 0 | 0 | 72 | 72 |

## Per query

| Query | Context | Expected | Runs (model:run outcome [fired]) |
|---|---|---|---|
| author-01 | airflow3 | authoring-airflow-dags | fable-5-1:1 hit [authoring-airflow-dags]; fable-5-1:2 hit [authoring-airflow-dags]; opus-5-5:1 hit [authoring-airflow-dags]; opus-5-5:2 hit [authoring-airflow-dags]; sonnet-5-5:1 hit [authoring-airflow-dags]; sonnet-5-5:2 hit [authoring-airflow-dags] |
| author-02 | airflow2 | authoring-airflow-dags | fable-5-1:1 hit [authoring-airflow-dags]; fable-5-1:2 hit [authoring-airflow-dags]; opus-5-5:1 hit [authoring-airflow-dags]; opus-5-5:2 hit [authoring-airflow-dags]; sonnet-5-5:1 miss; sonnet-5-5:2 hit [authoring-airflow-dags] |
| author-03 | airflow3 | authoring-airflow-dags | fable-5-1:1 hit [authoring-airflow-dags]; fable-5-1:2 hit [authoring-airflow-dags]; opus-5-5:1 hit [authoring-airflow-dags]; opus-5-5:2 hit [authoring-airflow-dags]; sonnet-5-5:1 hit [authoring-airflow-dags]; sonnet-5-5:2 hit [authoring-airflow-dags] |
| author-04 | airflow2 | authoring-airflow-dags | fable-5-1:1 hit [authoring-airflow-dags]; fable-5-1:2 hit [authoring-airflow-dags]; opus-5-5:1 hit [authoring-airflow-dags]; opus-5-5:2 hit [authoring-airflow-dags]; sonnet-5-5:1 hit [authoring-airflow-dags]; sonnet-5-5:2 hit [authoring-airflow-dags] |
| author-05 | airflow3 | authoring-airflow-dags | fable-5-1:1 hit [authoring-airflow-dags]; fable-5-1:2 hit [authoring-airflow-dags]; opus-5-5:1 hit [authoring-airflow-dags]; opus-5-5:2 hit [authoring-airflow-dags]; sonnet-5-5:1 miss; sonnet-5-5:2 miss |
| author-06 | airflow3 | authoring-airflow-dags | fable-5-1:1 hit [authoring-airflow-dags]; fable-5-1:2 hit [authoring-airflow-dags]; opus-5-5:1 hit [authoring-airflow-dags]; opus-5-5:2 hit [authoring-airflow-dags]; sonnet-5-5:1 miss; sonnet-5-5:2 miss |
| migrate-01 | airflow2 | migrating-to-airflow-3 | fable-5-1:1 hit [migrating-to-airflow-3]; fable-5-1:2 hit [migrating-to-airflow-3]; opus-5-5:1 hit [migrating-to-airflow-3]; opus-5-5:2 hit [migrating-to-airflow-3]; sonnet-5-5:1 hit [migrating-to-airflow-3]; sonnet-5-5:2 hit [migrating-to-airflow-3] |
| migrate-02 | airflow2 | migrating-to-airflow-3 | fable-5-1:1 hit [migrating-to-airflow-3]; fable-5-1:2 hit [migrating-to-airflow-3]; opus-5-5:1 hit [migrating-to-airflow-3]; opus-5-5:2 hit [migrating-to-airflow-3]; sonnet-5-5:1 hit [migrating-to-airflow-3]; sonnet-5-5:2 hit [migrating-to-airflow-3] |
| migrate-03 | airflow2 | migrating-to-airflow-3 | fable-5-1:1 hit [migrating-to-airflow-3]; fable-5-1:2 hit [migrating-to-airflow-3]; opus-5-5:1 hit [migrating-to-airflow-3]; opus-5-5:2 hit [migrating-to-airflow-3]; sonnet-5-5:1 hit [migrating-to-airflow-3]; sonnet-5-5:2 hit [migrating-to-airflow-3] |
| migrate-04 | airflow2 | migrating-to-airflow-3 | fable-5-1:1 hit [migrating-to-airflow-3]; fable-5-1:2 hit [migrating-to-airflow-3]; opus-5-5:1 hit [migrating-to-airflow-3]; opus-5-5:2 hit [migrating-to-airflow-3]; sonnet-5-5:1 hit [migrating-to-airflow-3]; sonnet-5-5:2 hit [migrating-to-airflow-3] |
| migrate-05 | airflow2 | migrating-to-airflow-3 | fable-5-1:1 hit [migrating-to-airflow-3]; fable-5-1:2 hit [migrating-to-airflow-3]; opus-5-5:1 hit [migrating-to-airflow-3]; opus-5-5:2 hit [migrating-to-airflow-3]; sonnet-5-5:1 hit [migrating-to-airflow-3]; sonnet-5-5:2 hit [migrating-to-airflow-3] |
| migrate-06 | airflow2 | migrating-to-airflow-3 | fable-5-1:1 hit [migrating-to-airflow-3]; fable-5-1:2 hit [migrating-to-airflow-3]; opus-5-5:1 hit [migrating-to-airflow-3]; opus-5-5:2 hit [migrating-to-airflow-3]; sonnet-5-5:1 hit [migrating-to-airflow-3]; sonnet-5-5:2 hit [migrating-to-airflow-3] |
| near-cron | python | - | fable-5-1:1 quiet; fable-5-1:2 quiet; opus-5-5:1 quiet; opus-5-5:2 quiet; sonnet-5-5:1 quiet; sonnet-5-5:2 quiet |
| near-dagster | python | - | fable-5-1:1 quiet; fable-5-1:2 quiet; opus-5-5:1 quiet; opus-5-5:2 quiet; sonnet-5-5:1 quiet; sonnet-5-5:2 quiet |
| near-databricks-job | dbt | - | fable-5-1:1 quiet; fable-5-1:2 quiet; opus-5-5:1 quiet; opus-5-5:2 quiet; sonnet-5-5:1 quiet; sonnet-5-5:2 quiet |
| near-dbt-debug | dbt | - | fable-5-1:1 quiet [debugging-dbt-errors]; fable-5-1:2 quiet [debugging-dbt-errors]; opus-5-5:1 quiet [debugging-dbt-errors]; opus-5-5:2 quiet [debugging-dbt-errors]; sonnet-5-5:1 quiet [debugging-dbt-errors]; sonnet-5-5:2 quiet [debugging-dbt-errors] |
| near-dbt-model | dbt | - | fable-5-1:1 quiet [creating-dbt-models]; fable-5-1:2 quiet [creating-dbt-models]; opus-5-5:1 quiet [creating-dbt-models]; opus-5-5:2 quiet [creating-dbt-models]; sonnet-5-5:1 quiet [creating-dbt-models]; sonnet-5-5:2 quiet [creating-dbt-models] |
| near-dbt-test | dbt | - | fable-5-1:1 quiet [testing-dbt-models]; fable-5-1:2 quiet [testing-dbt-models]; opus-5-5:1 quiet [testing-dbt-models]; opus-5-5:2 quiet [testing-dbt-models]; sonnet-5-5:1 quiet [testing-dbt-models]; sonnet-5-5:2 quiet [testing-dbt-models] |
| near-gha | python | - | fable-5-1:1 quiet; fable-5-1:2 quiet; opus-5-5:1 quiet; opus-5-5:2 quiet; sonnet-5-5:1 quiet; sonnet-5-5:2 quiet |
| near-prefect | python | - | fable-5-1:1 quiet; fable-5-1:2 quiet; opus-5-5:1 quiet; opus-5-5:2 quiet; sonnet-5-5:1 quiet; sonnet-5-5:2 quiet |
| near-pytest | python | - | fable-5-1:1 quiet; fable-5-1:2 quiet; opus-5-5:1 quiet; opus-5-5:2 quiet; sonnet-5-5:1 quiet; sonnet-5-5:2 quiet |
| near-snowflake | dbt | - | fable-5-1:1 quiet [optimizing-query-text]; fable-5-1:2 quiet [optimizing-query-text]; opus-5-5:1 quiet [optimizing-query-text]; opus-5-5:2 quiet [optimizing-query-text]; sonnet-5-5:1 quiet [optimizing-query-text]; sonnet-5-5:2 quiet [optimizing-query-text] |
| near-what-dag | python | - | fable-5-1:1 quiet; fable-5-1:2 quiet; opus-5-5:1 quiet; opus-5-5:2 quiet; sonnet-5-5:1 quiet; sonnet-5-5:2 quiet |
| near-wrong-day-script | python | - | fable-5-1:1 quiet; fable-5-1:2 quiet; opus-5-5:1 quiet; opus-5-5:2 quiet; sonnet-5-5:1 quiet; sonnet-5-5:2 quiet |
| test-01 | airflow3 | testing-airflow-dags | fable-5-1:1 hit [testing-airflow-dags]; fable-5-1:2 hit [testing-airflow-dags]; opus-5-5:1 hit [testing-airflow-dags]; opus-5-5:2 hit [testing-airflow-dags]; sonnet-5-5:1 hit [testing-airflow-dags]; sonnet-5-5:2 hit [testing-airflow-dags] |
| test-02 | airflow2 | testing-airflow-dags | fable-5-1:1 hit [testing-airflow-dags]; fable-5-1:2 hit [testing-airflow-dags]; opus-5-5:1 hit [testing-airflow-dags]; opus-5-5:2 hit [testing-airflow-dags]; sonnet-5-5:1 hit [testing-airflow-dags]; sonnet-5-5:2 hit [testing-airflow-dags] |
| test-03 | airflow3 | testing-airflow-dags | fable-5-1:1 hit [testing-airflow-dags]; fable-5-1:2 hit [testing-airflow-dags]; opus-5-5:1 hit [testing-airflow-dags]; opus-5-5:2 hit [testing-airflow-dags]; sonnet-5-5:1 hit [testing-airflow-dags]; sonnet-5-5:2 hit [testing-airflow-dags] |
| test-04 | airflow2 | testing-airflow-dags | fable-5-1:1 hit [testing-airflow-dags]; fable-5-1:2 hit [testing-airflow-dags]; opus-5-5:1 hit [testing-airflow-dags]; opus-5-5:2 hit [testing-airflow-dags]; sonnet-5-5:1 hit [testing-airflow-dags]; sonnet-5-5:2 hit [testing-airflow-dags] |
| test-05 | airflow3 | testing-airflow-dags | fable-5-1:1 hit [testing-airflow-dags]; fable-5-1:2 hit [testing-airflow-dags]; opus-5-5:1 hit [testing-airflow-dags]; opus-5-5:2 hit [testing-airflow-dags]; sonnet-5-5:1 hit [testing-airflow-dags]; sonnet-5-5:2 hit [testing-airflow-dags] |
| test-06 | airflow3 | testing-airflow-dags | fable-5-1:1 hit [testing-airflow-dags]; fable-5-1:2 hit [testing-airflow-dags]; opus-5-5:1 hit [testing-airflow-dags]; opus-5-5:2 hit [testing-airflow-dags]; sonnet-5-5:1 miss; sonnet-5-5:2 hit [testing-airflow-dags] |

## Notable misfires

- **miss** `author-02` (sonnet-5-5 run 1): expected authoring-airflow-dags, fired nothing. Query: "customer_sync doesn't show up in the UI anymore, I think it has an import error. Can you fix it?"
- **miss** `author-05` (sonnet-5-5 run 1): expected authoring-airflow-dags, fired nothing. Query: "Every time we rerun the events job it duplicates rows in analytics.events. Make it safe to rerun and backfill."
- **miss** `author-05` (sonnet-5-5 run 2): expected authoring-airflow-dags, fired nothing. Query: "Every time we rerun the events job it duplicates rows in analytics.events. Make it safe to rerun and backfill."
- **miss** `author-06` (sonnet-5-5 run 1): expected authoring-airflow-dags, fired nothing. Query: "In the orders pipeline, pass the number of rows loaded from the load step to the notify step so the message says how many orders came in."
- **miss** `author-06` (sonnet-5-5 run 2): expected authoring-airflow-dags, fired nothing. Query: "In the orders pipeline, pass the number of rows loaded from the load step to the notify step so the message says how many orders came in."
- **miss** `test-06` (sonnet-5-5 run 1): expected testing-airflow-dags, fired nothing. Query: "I want a test that runs the orders pipeline end to end on the sample data in tests/data and checks the output."
