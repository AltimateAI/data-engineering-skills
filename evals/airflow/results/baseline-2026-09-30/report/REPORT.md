# Airflow skill eval report

Pass rate = fraction of valid runs whose primary checks all passed. Excluded runs (infra_error, grader_error, skipped_budget) are listed but not counted.

## dev: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 39 (26) | 38% | 0.664 | 0.676 | 0% | 3.99e+06 | 0.616 | 211 | {'ok': 10, 'task_fail': 11, 'turn_limit': 5, 'skipped_budget': 13} |
| baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 39 (26) | 58% | 0.822 | 0.705 | 0% | 2.83e+06 | 1.43 | 188 | {'ok': 15, 'task_fail': 8, 'turn_limit': 3, 'skipped_budget': 13} |

## dev: per case

| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| authoring-airflow2-inventory-snapshot | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 100% | 1 | 0.667 | - | 0.373 | {'ok': 2, 'skipped_budget': 1} |
| authoring-airflow2-inventory-snapshot | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 100% | 1 | 0.667 | - | 0.734 | {'ok': 2, 'skipped_budget': 1} |
| authoring-clickstream-claim-check | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 50% | 0.929 | 0.833 | - | 0.571 | {'task_fail': 1, 'ok': 1, 'skipped_budget': 1} |
| authoring-clickstream-claim-check | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 100% | 1 | 0.667 | - | 1.25 | {'ok': 2, 'skipped_budget': 1} |
| authoring-vendor-shipments-etl | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 50% | 0.958 | 0.667 | - | 0.589 | {'ok': 1, 'task_fail': 1, 'skipped_budget': 1} |
| authoring-vendor-shipments-etl | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 100% | 1 | 0.5 | - | 1.43 | {'ok': 2, 'skipped_budget': 1} |
| debugging-manual-trigger-context | debugging | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 0% | 0.714 | 0.667 | - | 0.282 | {'task_fail': 2, 'skipped_budget': 1} |
| debugging-manual-trigger-context | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 0% | 0.786 | 0.667 | - | 0.773 | {'task_fail': 2, 'skipped_budget': 1} |
| debugging-variable-at-parse | debugging | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 100% | 1 | 0.833 | - | 0.444 | {'ok': 2, 'skipped_budget': 1} |
| debugging-variable-at-parse | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 0% | 0 | 0.333 | - | 0.948 | {'task_fail': 2, 'skipped_budget': 1} |
| migration-inventory-context | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 0% | 0.6 | 0.167 | - | 0.46 | {'task_fail': 2, 'skipped_budget': 1} |
| migration-inventory-context | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 0% | 0.8 | 0.333 | - | 1.22 | {'task_fail': 2, 'skipped_budget': 1} |
| migration-revenue-previous-day | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 0% | 0.5 | 0.667 | - | 0.749 | {'turn_limit': 2, 'skipped_budget': 1} |
| migration-revenue-previous-day | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 0% | 0.714 | 0.667 | - | 2.33 | {'turn_limit': 1, 'task_fail': 1, 'skipped_budget': 1} |
| migration-weekly-catchup | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 0% | 0.357 | 0.167 | - | 0.76 | {'task_fail': 2, 'skipped_budget': 1} |
| migration-weekly-catchup | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 0% | 0.714 | 0.833 | - | 2.92 | {'turn_limit': 2, 'skipped_budget': 1} |
| scheduling-idempotent-orders-load | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 50% | 0.75 | 0.833 | - | 0.89 | {'task_fail': 1, 'ok': 1, 'skipped_budget': 1} |
| scheduling-idempotent-orders-load | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 50% | 0.667 | 0.833 | - | 1.11 | {'task_fail': 1, 'ok': 1, 'skipped_budget': 1} |
| scheduling-weekday-ny-business-day | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 0% | 0.143 | 0.667 | - | 0.595 | {'task_fail': 2, 'skipped_budget': 1} |
| scheduling-weekday-ny-business-day | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 100% | 1 | 0.667 | - | 0.829 | {'ok': 2, 'skipped_budget': 1} |
| testing-airflow2-ci-suite | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 100% | 1 | 1 | - | 0.64 | {'ok': 2, 'skipped_budget': 1} |
| testing-airflow2-ci-suite | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 100% | 1 | 1 | - | 2.06 | {'ok': 2, 'skipped_budget': 1} |
| testing-custom-operator-conn | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 0% | 0.125 | 0.875 | - | 0.959 | {'turn_limit': 2, 'skipped_budget': 1} |
| testing-custom-operator-conn | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 100% | 1 | 1 | - | 1.74 | {'ok': 2, 'skipped_budget': 1} |
| testing-dagbag-integrity | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 50% | 0.562 | 0.75 | - | 0.695 | {'turn_limit': 1, 'ok': 1, 'skipped_budget': 1} |
| testing-dagbag-integrity | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 100% | 1 | 1 | - | 1.27 | {'ok': 2, 'skipped_budget': 1} |

## holdout: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 21 (14) | 14% | 0.546 | 0.762 | 0% | 3.9e+06 | 0.643 | 226 | {'ok': 2, 'turn_limit': 2, 'task_fail': 10, 'skipped_budget': 7} |
| baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 21 (14) | 36% | 0.812 | 0.667 | 0% | 2.8e+06 | 1.52 | 201 | {'ok': 5, 'task_fail': 9, 'skipped_budget': 7} |

## holdout: per case

| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| authoring-daily-revenue-yesterday | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 50% | 0.833 | 1 | - | 0.701 | {'ok': 1, 'task_fail': 1, 'skipped_budget': 1} |
| authoring-daily-revenue-yesterday | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 50% | 0.833 | 0.667 | - | 1.18 | {'ok': 1, 'task_fail': 1, 'skipped_budget': 1} |
| authoring-partner-feeds-mapping | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 0% | 0.444 | 0.833 | - | 0.854 | {'turn_limit': 2, 'skipped_budget': 1} |
| authoring-partner-feeds-mapping | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 100% | 1 | 0.5 | - | 1.38 | {'ok': 2, 'skipped_budget': 1} |
| debugging-nondeterministic-parse | debugging | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 50% | 0.95 | 0.833 | - | 0.749 | {'ok': 1, 'task_fail': 1, 'skipped_budget': 1} |
| debugging-nondeterministic-parse | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 100% | 1 | 0.667 | - | 0.811 | {'ok': 2, 'skipped_budget': 1} |
| migration-hourly-pageviews-templates | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 0% | 0.357 | 0.333 | - | 0.648 | {'task_fail': 2, 'skipped_budget': 1} |
| migration-hourly-pageviews-templates | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 0% | 0.571 | 0.5 | - | 2.22 | {'task_fail': 2, 'skipped_budget': 1} |
| migration-shipments-assets | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 0% | 0 | 0.667 | - | 0.463 | {'task_fail': 2, 'skipped_budget': 1} |
| migration-shipments-assets | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 0% | 0.571 | 0.667 | - | 2.43 | {'task_fail': 2, 'skipped_budget': 1} |
| scheduling-backfill-pageviews | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 0% | 0.611 | 0.667 | - | 0.395 | {'task_fail': 2, 'skipped_budget': 1} |
| scheduling-backfill-pageviews | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 0% | 0.833 | 0.667 | - | 0.938 | {'task_fail': 2, 'skipped_budget': 1} |
| testing-taskflow-transforms | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (2) | 0% | 0.625 | 1 | - | 0.688 | {'task_fail': 2, 'skipped_budget': 1} |
| testing-taskflow-transforms | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (2) | 0% | 0.875 | 1 | - | 1.7 | {'task_fail': 2, 'skipped_budget': 1} |

## Failure classes (all runs)

{'ok': 32, 'task_fail': 38, 'turn_limit': 10, 'skipped_budget': 40}

## Sources

- `evals/airflow/results/baseline-2026-09-30`: arm=baseline models=['google-vertex-anthropic/claude-sonnet-4-6@default', 'google-vertex-anthropic/claude-haiku-4-5@20251001'] altimate-code=0.12.2 started=2026-09-30T11:53:13+00:00 budget={'cap_usd': 80.0, 'per_run_cap_usd': 5.0, 'spent_usd': 83.57, 'stopped_early': True}
