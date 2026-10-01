# Airflow skill eval report

Pass rate = fraction of valid runs whose primary checks all passed. Excluded runs (infra_error, grader_error, skipped_budget) are listed but not counted.

## dev: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 39 (39) | 36% | 0.664 | 0.694 | 0% | 3.89e+06 | 0.643 | 187 | {'ok': 14, 'task_fail': 18, 'turn_limit': 7} |
| baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 39 (39) | 56% | 0.806 | 0.718 | 0% | 2.82e+06 | 1.46 | 170 | {'ok': 22, 'task_fail': 12, 'turn_limit': 5} |

## dev: per case

| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| authoring-airflow2-inventory-snapshot | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.857 | 0.667 | - | 0.35 | {'ok': 2, 'task_fail': 1} |
| authoring-airflow2-inventory-snapshot | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.667 | - | 0.722 | {'ok': 3} |
| authoring-clickstream-claim-check | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.905 | 0.889 | - | 0.924 | {'task_fail': 2, 'ok': 1} |
| authoring-clickstream-claim-check | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.778 | - | 1.36 | {'ok': 3} |
| authoring-vendor-shipments-etl | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.944 | 0.667 | - | 0.605 | {'ok': 1, 'task_fail': 2} |
| authoring-vendor-shipments-etl | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.556 | - | 1.35 | {'ok': 3} |
| debugging-manual-trigger-context | debugging | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.714 | 0.667 | - | 0.392 | {'task_fail': 3} |
| debugging-manual-trigger-context | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.762 | 0.667 | - | 0.816 | {'task_fail': 3} |
| debugging-variable-at-parse | debugging | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 0.778 | - | 0.447 | {'ok': 3} |
| debugging-variable-at-parse | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0 | 0.333 | - | 1 | {'task_fail': 3} |
| migration-inventory-context | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.533 | 0.222 | - | 0.572 | {'task_fail': 3} |
| migration-inventory-context | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.8 | 0.444 | - | 1.48 | {'task_fail': 3} |
| migration-revenue-previous-day | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.476 | 0.667 | - | 0.755 | {'turn_limit': 3} |
| migration-revenue-previous-day | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.762 | 0.667 | - | 2.41 | {'turn_limit': 2, 'task_fail': 1} |
| migration-weekly-catchup | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.333 | 0.333 | - | 0.827 | {'task_fail': 2, 'turn_limit': 1} |
| migration-weekly-catchup | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.714 | 0.778 | - | 2.74 | {'turn_limit': 3} |
| scheduling-idempotent-orders-load | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.611 | 0.889 | - | 0.778 | {'task_fail': 2, 'ok': 1} |
| scheduling-idempotent-orders-load | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 67% | 0.778 | 0.778 | - | 0.993 | {'task_fail': 1, 'ok': 2} |
| scheduling-weekday-ny-business-day | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.429 | 0.667 | - | 0.505 | {'task_fail': 2, 'ok': 1} |
| scheduling-weekday-ny-business-day | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 67% | 0.667 | 0.667 | - | 0.844 | {'ok': 2, 'task_fail': 1} |
| testing-airflow2-ci-suite | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 1 | - | 0.713 | {'ok': 3} |
| testing-airflow2-ci-suite | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | - | 2.04 | {'ok': 3} |
| testing-custom-operator-conn | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.125 | 0.833 | - | 0.762 | {'turn_limit': 2, 'task_fail': 1} |
| testing-custom-operator-conn | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | - | 1.86 | {'ok': 3} |
| testing-dagbag-integrity | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.708 | 0.75 | - | 0.73 | {'turn_limit': 1, 'ok': 2} |
| testing-dagbag-integrity | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | - | 1.31 | {'ok': 3} |

## holdout: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 21 (21) | 19% | 0.525 | 0.714 | 0% | 3.82e+06 | 0.683 | 199 | {'ok': 4, 'turn_limit': 2, 'task_fail': 15} |
| baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 21 (21) | 38% | 0.802 | 0.667 | 0% | 3.04e+06 | 1.88 | 200 | {'ok': 8, 'task_fail': 12, 'cost_limit': 1} |

## holdout: per case

| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| authoring-daily-revenue-yesterday | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.889 | 0.889 | - | 0.814 | {'ok': 2, 'task_fail': 1} |
| authoring-daily-revenue-yesterday | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 33% | 0.778 | 0.778 | - | 2.54 | {'ok': 1, 'task_fail': 1, 'cost_limit': 1} |
| authoring-partner-feeds-mapping | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.444 | 0.889 | - | 0.816 | {'turn_limit': 2, 'task_fail': 1} |
| authoring-partner-feeds-mapping | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.556 | - | 1.79 | {'ok': 3} |
| debugging-nondeterministic-parse | debugging | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.967 | 0.778 | - | 0.711 | {'ok': 2, 'task_fail': 1} |
| debugging-nondeterministic-parse | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.667 | - | 0.863 | {'ok': 3} |
| migration-hourly-pageviews-templates | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.429 | 0.222 | - | 0.662 | {'task_fail': 3} |
| migration-hourly-pageviews-templates | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.571 | 0.444 | - | 2.14 | {'task_fail': 3} |
| migration-shipments-assets | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0 | 0.556 | - | 0.474 | {'task_fail': 3} |
| migration-shipments-assets | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.571 | 0.556 | - | 2.58 | {'task_fail': 3} |
| scheduling-backfill-pageviews | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.407 | 0.667 | - | 0.54 | {'task_fail': 3} |
| scheduling-backfill-pageviews | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.778 | 0.667 | - | 1.12 | {'task_fail': 3} |
| testing-taskflow-transforms | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.542 | 1 | - | 0.767 | {'task_fail': 3} |
| testing-taskflow-transforms | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 33% | 0.917 | 1 | - | 2.12 | {'task_fail': 2, 'ok': 1} |

## Failure classes (all runs)

{'ok': 48, 'task_fail': 57, 'turn_limit': 14, 'cost_limit': 1}

40 skipped_budget placeholder row(s) were replaced by launched runs from another result dir.

## Sources

- `evals/airflow/results/baseline-2026-09-30`: arm=baseline models=['google-vertex-anthropic/claude-sonnet-4-6@default', 'google-vertex-anthropic/claude-haiku-4-5@20251001'] altimate-code=0.12.2 started=2026-09-30T11:53:13+00:00 budget={'cap_usd': 80.0, 'per_run_cap_usd': 5.0, 'spent_usd': 83.57, 'stopped_early': True}
- `evals/airflow/results/baseline-run3-2026-09-30`: arm=baseline models=['google-vertex-anthropic/claude-sonnet-4-6@default', 'google-vertex-anthropic/claude-haiku-4-5@20251001'] altimate-code=0.12.2 started=2026-09-30T15:24:19+00:00 budget={'cap_usd': 55.0, 'per_run_cap_usd': 5.0, 'spent_usd': 52.105, 'stopped_early': False, 'spent_usd_harness': 46.8305}
