# Airflow skill trigger eval: triggers-2026-09-30

- Models: google-vertex-anthropic/claude-sonnet-4-6@default, google-vertex-anthropic/claude-haiku-4-5@20251001; runs per query: 2; max turns: 4
- Queries: 30 (18 should-fire, 12 near-miss); skill arm (repo skills + skills/airflow)
- skills/airflow sha256: `e03e9d6dbfd25d119b2586f509d4fce86bcfd8d5b243fa25994516fb246b0a19`
- Spent: $44.59 of $40.00 cap

Recall = should-fire runs where the expected skill fired. Precision = runs where the skill fired that expected it. Confusion = the skill's own should-fire runs where a different Airflow skill fired. Near-miss false-fire = near-miss runs where the skill fired.

## All models

| Skill | Recall | Precision | Confusion | Near-miss false-fire |
|---|---|---|---|---|
| authoring-airflow-dags | 14/24 (58%) | 88% (16 fired) | 0/24 (0%) | 2/24 (8%) |
| migrating-to-airflow-3 | 16/19 (84%) | 100% (16 fired) | 0/19 (0%) | 0/24 (0%) |
| testing-airflow-dags | 7/12 (58%) | 100% (7 fired) | 0/12 (0%) | 0/24 (0%) |

Any Airflow skill on near-misses: 2/24 (8%). Outcomes: {"false_fire": 2, "hit": 37, "miss": 18, "quiet": 22}.
Unscored runs: {"skipped_budget": 41}.

## google-vertex-anthropic/claude-sonnet-4-6@default

| Skill | Recall | Precision | Confusion | Near-miss false-fire |
|---|---|---|---|---|
| authoring-airflow-dags | 10/12 (83%) | 83% (12 fired) | 0/12 (0%) | 2/12 (17%) |
| migrating-to-airflow-3 | 10/10 (100%) | 100% (10 fired) | 0/10 (0%) | 0/12 (0%) |
| testing-airflow-dags | 6/6 (100%) | 100% (6 fired) | 0/6 (0%) | 0/12 (0%) |

Any Airflow skill on near-misses: 2/12 (17%). Outcomes: {"false_fire": 2, "hit": 26, "miss": 2, "quiet": 10}.
Unscored runs: {"skipped_budget": 20}.

## google-vertex-anthropic/claude-haiku-4-5@20251001

| Skill | Recall | Precision | Confusion | Near-miss false-fire |
|---|---|---|---|---|
| authoring-airflow-dags | 4/12 (33%) | 100% (4 fired) | 0/12 (0%) | 0/12 (0%) |
| migrating-to-airflow-3 | 6/9 (67%) | 100% (6 fired) | 0/9 (0%) | 0/12 (0%) |
| testing-airflow-dags | 1/6 (17%) | 100% (1 fired) | 0/6 (0%) | 0/12 (0%) |

Any Airflow skill on near-misses: 0/12 (0%). Outcomes: {"hit": 11, "miss": 16, "quiet": 12}.
Unscored runs: {"skipped_budget": 21}.

## Confusion matrix (all models, runs)

| expected \ fired | authoring-airflow-dags | migrating-to-airflow-3 | testing-airflow-dags | (no airflow skill) | runs |
|---|---|---|---|---|---|
| authoring-airflow-dags | 14 | 0 | 0 | 10 | 24 |
| migrating-to-airflow-3 | 0 | 16 | 0 | 3 | 19 |
| testing-airflow-dags | 0 | 0 | 7 | 5 | 12 |
| near-miss (none) | 2 | 0 | 0 | 22 | 24 |

## Per query

| Query | Context | Expected | Runs (model:run outcome [fired]) |
|---|---|---|---|
| author-01 | airflow3 | authoring-airflow-dags | haiku:1 hit [authoring-airflow-dags]; haiku:2 hit [authoring-airflow-dags]; sonnet:1 hit [authoring-airflow-dags]; sonnet:2 hit [authoring-airflow-dags] |
| author-02 | airflow2 | authoring-airflow-dags | haiku:1 miss; haiku:2 miss; sonnet:1 hit [authoring-airflow-dags]; sonnet:2 hit [authoring-airflow-dags] |
| author-03 | airflow3 | authoring-airflow-dags | haiku:1 hit [authoring-airflow-dags]; haiku:2 miss; sonnet:1 hit [authoring-airflow-dags]; sonnet:2 hit [authoring-airflow-dags] |
| author-04 | airflow2 | authoring-airflow-dags | haiku:1 miss; haiku:2 hit [authoring-airflow-dags]; sonnet:1 hit [authoring-airflow-dags]; sonnet:2 hit [authoring-airflow-dags] |
| author-05 | airflow3 | authoring-airflow-dags | haiku:1 miss; haiku:2 miss; sonnet:1 hit [authoring-airflow-dags]; sonnet:2 miss [developing-incremental-models] |
| author-06 | airflow3 | authoring-airflow-dags | haiku:1 miss; haiku:2 miss; sonnet:1 hit [authoring-airflow-dags]; sonnet:2 miss |
| migrate-01 | airflow2 | migrating-to-airflow-3 | haiku:1 hit [migrating-to-airflow-3]; haiku:2 miss; sonnet:1 hit [migrating-to-airflow-3]; sonnet:2 hit [migrating-to-airflow-3] |
| migrate-02 | airflow2 | migrating-to-airflow-3 | haiku:1 hit [migrating-to-airflow-3]; haiku:2 hit [migrating-to-airflow-3]; sonnet:1 hit [migrating-to-airflow-3]; sonnet:2 hit [migrating-to-airflow-3] |
| migrate-03 | airflow2 | migrating-to-airflow-3 | haiku:1 hit [migrating-to-airflow-3]; haiku:2 hit [migrating-to-airflow-3]; sonnet:1 hit [migrating-to-airflow-3]; sonnet:2 hit [migrating-to-airflow-3] |
| migrate-04 | airflow2 | migrating-to-airflow-3 | haiku:1 hit [migrating-to-airflow-3]; haiku:2 skipped_budget; sonnet:1 hit [migrating-to-airflow-3]; sonnet:2 hit [migrating-to-airflow-3] |
| migrate-05 | airflow2 | migrating-to-airflow-3 | haiku:1 miss; haiku:2 skipped_budget; sonnet:1 hit [migrating-to-airflow-3]; sonnet:2 skipped_budget |
| migrate-06 | airflow2 | migrating-to-airflow-3 | haiku:1 miss; haiku:2 skipped_budget; sonnet:1 hit [migrating-to-airflow-3]; sonnet:2 skipped_budget |
| near-cron | python | - | haiku:1 quiet; haiku:2 skipped_budget; sonnet:1 quiet; sonnet:2 skipped_budget |
| near-dagster | python | - | haiku:1 quiet; haiku:2 skipped_budget; sonnet:1 quiet; sonnet:2 skipped_budget |
| near-databricks-job | dbt | - | haiku:1 quiet [dbt-develop, dbt-schema-verify]; haiku:2 skipped_budget; sonnet:1 quiet [dbt-develop, dbt-schema-verify]; sonnet:2 skipped_budget |
| near-dbt-debug | dbt | - | haiku:1 quiet [dbt-develop, dbt-schema-verify]; haiku:2 skipped_budget; sonnet:1 quiet [dbt-troubleshoot, dbt-develop, dbt-schema-verify]; sonnet:2 skipped_budget |
| near-dbt-model | dbt | - | haiku:1 quiet [dbt-develop, dbt-schema-verify]; haiku:2 skipped_budget; sonnet:1 quiet [dbt-develop, dbt-schema-verify]; sonnet:2 skipped_budget |
| near-dbt-test | dbt | - | haiku:1 quiet [dbt-develop, dbt-schema-verify]; haiku:2 skipped_budget; sonnet:1 quiet [dbt-develop, dbt-schema-verify]; sonnet:2 skipped_budget |
| near-gha | python | - | haiku:1 quiet; haiku:2 skipped_budget; sonnet:1 quiet; sonnet:2 skipped_budget |
| near-prefect | python | - | haiku:1 quiet; haiku:2 skipped_budget; sonnet:1 false_fire [authoring-airflow-dags]; sonnet:2 skipped_budget |
| near-pytest | python | - | haiku:1 quiet; haiku:2 skipped_budget; sonnet:1 quiet; sonnet:2 skipped_budget |
| near-snowflake | dbt | - | haiku:1 quiet [dbt-develop, dbt-schema-verify]; haiku:2 skipped_budget; sonnet:1 quiet [optimizing-query-text, dbt-develop, dbt-schema-verify]; sonnet:2 skipped_budget |
| near-what-dag | python | - | haiku:1 quiet; haiku:2 skipped_budget; sonnet:1 quiet; sonnet:2 skipped_budget |
| near-wrong-day-script | python | - | haiku:1 quiet; haiku:2 skipped_budget; sonnet:1 false_fire [authoring-airflow-dags]; sonnet:2 skipped_budget |
| test-01 | airflow3 | testing-airflow-dags | haiku:1 miss; haiku:2 skipped_budget; sonnet:1 hit [testing-airflow-dags]; sonnet:2 skipped_budget |
| test-02 | airflow2 | testing-airflow-dags | haiku:1 miss; haiku:2 skipped_budget; sonnet:1 hit [testing-airflow-dags]; sonnet:2 skipped_budget |
| test-03 | airflow3 | testing-airflow-dags | haiku:1 miss; haiku:2 skipped_budget; sonnet:1 hit [testing-airflow-dags]; sonnet:2 skipped_budget |
| test-04 | airflow2 | testing-airflow-dags | haiku:1 miss; haiku:2 skipped_budget; sonnet:1 hit [testing-airflow-dags]; sonnet:2 skipped_budget |
| test-05 | airflow3 | testing-airflow-dags | haiku:1 hit [testing-airflow-dags]; haiku:2 skipped_budget; sonnet:1 hit [testing-airflow-dags]; sonnet:2 skipped_budget |
| test-06 | airflow3 | testing-airflow-dags | haiku:1 miss; haiku:2 skipped_budget; sonnet:1 hit [testing-airflow-dags]; sonnet:2 skipped_budget |

## Notable misfires

- **false_fire** `near-prefect` (sonnet run 1): expected none, fired ['authoring-airflow-dags']. Query: "Turn flows/etl.py into a Prefect flow with extract, transform and load as tasks, 3 retries each, deployed to run every hour."
- **false_fire** `near-wrong-day-script` (sonnet run 1): expected none, fired ['authoring-airflow-dags']. Query: "scripts/nightly_report.py sometimes reports on the wrong day around daylight saving changes. Fix the date logic so it always reports on yesterday in local time."
- **miss** `author-02` (haiku run 1): expected authoring-airflow-dags, fired nothing. Query: "customer_sync doesn't show up in the UI anymore, I think it has an import error. Can you fix it?"
- **miss** `author-02` (haiku run 2): expected authoring-airflow-dags, fired nothing. Query: "customer_sync doesn't show up in the UI anymore, I think it has an import error. Can you fix it?"
- **miss** `author-03` (haiku run 2): expected authoring-airflow-dags, fired nothing. Query: "The daily_revenue job is processing the wrong day. When it runs on the 5th it should aggregate the 4th, but it's aggregating the 5th. Please fix."
- **miss** `author-04` (haiku run 1): expected authoring-airflow-dags, fired nothing. Query: "Make the partner load wait until the partner's file for that day actually lands in S3 before it runs, and give up after 3 hours."
- **miss** `author-05` (haiku run 1): expected authoring-airflow-dags, fired nothing. Query: "Every time we rerun the events job it duplicates rows in analytics.events. Make it safe to rerun and backfill."
- **miss** `author-05` (haiku run 2): expected authoring-airflow-dags, fired nothing. Query: "Every time we rerun the events job it duplicates rows in analytics.events. Make it safe to rerun and backfill."
- **miss** `author-05` (sonnet run 2): expected authoring-airflow-dags, fired ['developing-incremental-models']. Query: "Every time we rerun the events job it duplicates rows in analytics.events. Make it safe to rerun and backfill."
- **miss** `author-06` (haiku run 1): expected authoring-airflow-dags, fired nothing. Query: "In the orders pipeline, pass the number of rows loaded from the load step to the notify step so the message says how many orders came in."
- **miss** `author-06` (haiku run 2): expected authoring-airflow-dags, fired nothing. Query: "In the orders pipeline, pass the number of rows loaded from the load step to the notify step so the message says how many orders came in."
- **miss** `author-06` (sonnet run 2): expected authoring-airflow-dags, fired nothing. Query: "In the orders pipeline, pass the number of rows loaded from the load step to the notify step so the message says how many orders came in."
- **miss** `migrate-01` (haiku run 2): expected migrating-to-airflow-3, fired nothing. Query: "We're moving to Airflow 3.3 next month. Port the DAGs in this repo so they work there."
- **miss** `migrate-05` (haiku run 1): expected migrating-to-airflow-3, fired nothing. Query: "Get this project running on the new 3.x virtualenv without changing which dates each run processes."
- **miss** `migrate-06` (haiku run 1): expected migrating-to-airflow-3, fired nothing. Query: "Remove everything in these DAGs that won't exist in Airflow 3: execution_date, next_ds, DummyOperator, provide_context, the sla argument."
- **miss** `test-01` (haiku run 1): expected testing-airflow-dags, fired nothing. Query: "Add a pytest suite for our dags."
- **miss** `test-02` (haiku run 1): expected testing-airflow-dags, fired nothing. Query: "Make CI fail when any file in dags/ doesn't import."
- **miss** `test-03` (haiku run 1): expected testing-airflow-dags, fired nothing. Query: "Write tests that check every task has 2 retries and that orders_pipeline only runs on weekdays."
- **miss** `test-04` (haiku run 1): expected testing-airflow-dags, fired nothing. Query: "Add unit tests for WarehouseHook and WarehouseSqlOperator in plugins/. CI has no connections configured."
- **miss** `test-06` (haiku run 1): expected testing-airflow-dags, fired nothing. Query: "I want a test that runs the orders pipeline end to end on the sample data in tests/data and checks the output."
