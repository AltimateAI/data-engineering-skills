# Airflow skill eval report

Pass rate = fraction of valid runs whose primary checks all passed. Excluded runs (infra_error, grader_error, skipped_budget) are listed but not counted.

## dev: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 39 (39) | 36% | 0.664 | 0.694 | 0% | 3.89e+06 | 0.643 | 187 | {'ok': 14, 'task_fail': 18, 'turn_limit': 7} |
| baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 39 (39) | 56% | 0.806 | 0.718 | 0% | 2.82e+06 | 1.46 | 170 | {'ok': 22, 'task_fail': 12, 'turn_limit': 5} |
| skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 39 (39) | 79% | 0.908 | 0.917 | 90% | 3.81e+06 | 0.636 | 158 | {'ok': 31, 'task_fail': 6, 'turn_limit': 2} |
| skill | google-vertex-anthropic/claude-sonnet-4-6@default | 39 (39) | 95% | 0.993 | 0.906 | 100% | 3.91e+06 | 2.01 | 184 | {'ok': 37, 'task_fail': 2} |

## dev: paired delta (skill - baseline) over cases

| model | cases | delta pass rate | 95% CI | delta primary score | 95% CI |
|---|---|---|---|---|---|
| google-vertex-anthropic/claude-haiku-4-5@20251001 | 13 | 0.436 | (0.1795, 0.6667) | 0.244 | (0.0773, 0.4044) |
| google-vertex-anthropic/claude-sonnet-4-6@default | 13 | 0.385 | (0.1538, 0.6154) | 0.186 | (0.0672, 0.3517) |
| pooled (26 case x model pairs) | 13 | 0.41 | (0.2051, 0.6154) | 0.215 | (0.0974, 0.3263) |

Pooled CI: bootstrap over cases; a resampled case carries the deltas of all its models.

## dev: per case

| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| authoring-airflow2-inventory-snapshot | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.857 | 0.667 | - | 0.35 | {'ok': 2, 'task_fail': 1} |
| authoring-airflow2-inventory-snapshot | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.667 | - | 0.722 | {'ok': 3} |
| authoring-airflow2-inventory-snapshot | authoring | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.857 | 1 | {'authoring-airflow-dags': 3} | 0.691 | {'ok': 2, 'task_fail': 1} |
| authoring-airflow2-inventory-snapshot | authoring | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 1.31 | {'ok': 3} |
| authoring-clickstream-claim-check | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.905 | 0.889 | - | 0.924 | {'task_fail': 2, 'ok': 1} |
| authoring-clickstream-claim-check | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.778 | - | 1.36 | {'ok': 3} |
| authoring-clickstream-claim-check | authoring | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.809 | 1 | {'authoring-airflow-dags': 3} | 0.645 | {'ok': 2, 'task_fail': 1} |
| authoring-clickstream-claim-check | authoring | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 2.56 | {'ok': 3} |
| authoring-vendor-shipments-etl | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.944 | 0.667 | - | 0.605 | {'ok': 1, 'task_fail': 2} |
| authoring-vendor-shipments-etl | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.556 | - | 1.35 | {'ok': 3} |
| authoring-vendor-shipments-etl | authoring | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.861 | 0.778 | {'authoring-airflow-dags': 1} | 0.704 | {'ok': 1, 'task_fail': 2} |
| authoring-vendor-shipments-etl | authoring | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.667 | {'authoring-airflow-dags': 3} | 2.29 | {'ok': 3} |
| debugging-manual-trigger-context | debugging | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.714 | 0.667 | - | 0.392 | {'task_fail': 3} |
| debugging-manual-trigger-context | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.762 | 0.667 | - | 0.816 | {'task_fail': 3} |
| debugging-manual-trigger-context | debugging | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.905 | 0.889 | {'migrating-to-airflow-3': 3} | 0.607 | {'task_fail': 1, 'ok': 2} |
| debugging-manual-trigger-context | debugging | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 33% | 0.905 | 0.778 | {'migrating-to-airflow-3': 3} | 1.52 | {'task_fail': 2, 'ok': 1} |
| debugging-variable-at-parse | debugging | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 0.778 | - | 0.447 | {'ok': 3} |
| debugging-variable-at-parse | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0 | 0.333 | - | 1 | {'task_fail': 3} |
| debugging-variable-at-parse | debugging | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 1 | {'migrating-to-airflow-3': 3} | 0.387 | {'ok': 3} |
| debugging-variable-at-parse | debugging | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.778 | {'migrating-to-airflow-3': 3} | 1.11 | {'ok': 3} |
| migration-inventory-context | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.533 | 0.222 | - | 0.572 | {'task_fail': 3} |
| migration-inventory-context | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.8 | 0.444 | - | 1.48 | {'task_fail': 3} |
| migration-inventory-context | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 0.667 | {'migrating-to-airflow-3': 3} | 0.699 | {'ok': 3} |
| migration-inventory-context | migration | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.889 | {'migrating-to-airflow-3': 3} | 2.85 | {'ok': 3} |
| migration-revenue-previous-day | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.476 | 0.667 | - | 0.755 | {'turn_limit': 3} |
| migration-revenue-previous-day | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.762 | 0.667 | - | 2.41 | {'turn_limit': 2, 'task_fail': 1} |
| migration-revenue-previous-day | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 0.667 | {'migrating-to-airflow-3': 3} | 0.682 | {'ok': 3} |
| migration-revenue-previous-day | migration | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.667 | {'migrating-to-airflow-3': 3} | 3.06 | {'ok': 3} |
| migration-weekly-catchup | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.333 | 0.333 | - | 0.827 | {'task_fail': 2, 'turn_limit': 1} |
| migration-weekly-catchup | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.714 | 0.778 | - | 2.74 | {'turn_limit': 3} |
| migration-weekly-catchup | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 1 | {'migrating-to-airflow-3': 3} | 0.728 | {'ok': 3} |
| migration-weekly-catchup | migration | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'migrating-to-airflow-3': 3} | 2.73 | {'ok': 3} |
| scheduling-idempotent-orders-load | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.611 | 0.889 | - | 0.778 | {'task_fail': 2, 'ok': 1} |
| scheduling-idempotent-orders-load | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 67% | 0.778 | 0.778 | - | 0.993 | {'task_fail': 1, 'ok': 2} |
| scheduling-idempotent-orders-load | scheduling | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 0.581 | {'ok': 3} |
| scheduling-idempotent-orders-load | scheduling | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 1.83 | {'ok': 3} |
| scheduling-weekday-ny-business-day | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.429 | 0.667 | - | 0.505 | {'task_fail': 2, 'ok': 1} |
| scheduling-weekday-ny-business-day | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 67% | 0.667 | 0.667 | - | 0.844 | {'ok': 2, 'task_fail': 1} |
| scheduling-weekday-ny-business-day | scheduling | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 0.37 | {'ok': 3} |
| scheduling-weekday-ny-business-day | scheduling | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 1.58 | {'ok': 3} |
| testing-airflow2-ci-suite | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 1 | - | 0.713 | {'ok': 3} |
| testing-airflow2-ci-suite | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | - | 2.04 | {'ok': 3} |
| testing-airflow2-ci-suite | testing | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.708 | 1 | {'testing-airflow-dags': 3} | 0.891 | {'turn_limit': 1, 'ok': 2} |
| testing-airflow2-ci-suite | testing | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'testing-airflow-dags': 3} | 2.25 | {'ok': 3} |
| testing-custom-operator-conn | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.125 | 0.833 | - | 0.762 | {'turn_limit': 2, 'task_fail': 1} |
| testing-custom-operator-conn | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | - | 1.86 | {'ok': 3} |
| testing-custom-operator-conn | testing | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.708 | 0.917 | {'testing-airflow-dags': 2} | 0.693 | {'ok': 2, 'turn_limit': 1} |
| testing-custom-operator-conn | testing | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'testing-airflow-dags': 3} | 1.56 | {'ok': 3} |
| testing-dagbag-integrity | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.708 | 0.75 | - | 0.73 | {'turn_limit': 1, 'ok': 2} |
| testing-dagbag-integrity | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | - | 1.31 | {'ok': 3} |
| testing-dagbag-integrity | testing | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.958 | 1 | {'testing-airflow-dags': 2} | 0.597 | {'task_fail': 1, 'ok': 2} |
| testing-dagbag-integrity | testing | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'testing-airflow-dags': 3} | 1.45 | {'ok': 3} |

## holdout: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 21 (21) | 19% | 0.525 | 0.714 | 0% | 3.82e+06 | 0.683 | 199 | {'ok': 4, 'turn_limit': 2, 'task_fail': 15} |
| baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 21 (21) | 38% | 0.802 | 0.667 | 0% | 3.04e+06 | 1.88 | 200 | {'ok': 8, 'task_fail': 12, 'cost_limit': 1} |
| skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 21 (21) | 24% | 0.682 | 0.798 | 81% | 4.48e+06 | 0.809 | 183 | {'ok': 5, 'task_fail': 10, 'turn_limit': 6} |
| skill | google-vertex-anthropic/claude-sonnet-4-6@default | 21 (21) | 81% | 0.975 | 0.968 | 100% | 4.14e+06 | 2.44 | 239 | {'ok': 17, 'turn_limit': 1, 'task_fail': 3} |

## holdout: paired delta (skill - baseline) over cases

| model | cases | delta pass rate | 95% CI | delta primary score | 95% CI |
|---|---|---|---|---|---|
| google-vertex-anthropic/claude-haiku-4-5@20251001 | 7 | 0.0476 | (0.0, 0.1428) | 0.157 | (-0.0675, 0.415) |
| google-vertex-anthropic/claude-sonnet-4-6@default | 7 | 0.429 | (0.0476, 0.7619) | 0.173 | (0.0627, 0.288) |
| pooled (14 case x model pairs) | 7 | 0.238 | (0.0238, 0.4286) | 0.165 | (0.0231, 0.3235) |

Pooled CI: bootstrap over cases; a resampled case carries the deltas of all its models.

## holdout: per case

| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| authoring-daily-revenue-yesterday | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.889 | 0.889 | - | 0.814 | {'ok': 2, 'task_fail': 1} |
| authoring-daily-revenue-yesterday | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 33% | 0.778 | 0.778 | - | 2.54 | {'ok': 1, 'task_fail': 1, 'cost_limit': 1} |
| authoring-daily-revenue-yesterday | authoring | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.833 | 0.889 | {'authoring-airflow-dags': 2} | 1 | {'ok': 2, 'task_fail': 1} |
| authoring-daily-revenue-yesterday | authoring | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 3.66 | {'ok': 3} |
| authoring-partner-feeds-mapping | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.444 | 0.889 | - | 0.816 | {'turn_limit': 2, 'task_fail': 1} |
| authoring-partner-feeds-mapping | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.556 | - | 1.79 | {'ok': 3} |
| authoring-partner-feeds-mapping | authoring | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.667 | 0.889 | {'authoring-airflow-dags': 2} | 1.14 | {'task_fail': 1, 'turn_limit': 2} |
| authoring-partner-feeds-mapping | authoring | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.778 | {'authoring-airflow-dags': 3} | 3.21 | {'ok': 3} |
| debugging-nondeterministic-parse | debugging | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.967 | 0.778 | - | 0.711 | {'ok': 2, 'task_fail': 1} |
| debugging-nondeterministic-parse | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.667 | - | 0.863 | {'ok': 3} |
| debugging-nondeterministic-parse | debugging | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.967 | 1 | {'authoring-airflow-dags': 1, 'migrating-to-airflow-3': 3} | 0.525 | {'ok': 2, 'task_fail': 1} |
| debugging-nondeterministic-parse | debugging | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 67% | 0.967 | 1 | {'authoring-airflow-dags': 3} | 0.863 | {'ok': 2, 'task_fail': 1} |
| migration-hourly-pageviews-templates | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.429 | 0.222 | - | 0.662 | {'task_fail': 3} |
| migration-hourly-pageviews-templates | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.571 | 0.444 | - | 2.14 | {'task_fail': 3} |
| migration-hourly-pageviews-templates | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.571 | 0.556 | {'migrating-to-airflow-3': 3} | 0.708 | {'task_fail': 3} |
| migration-hourly-pageviews-templates | migration | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'migrating-to-airflow-3': 3} | 2.24 | {'ok': 3} |
| migration-shipments-assets | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0 | 0.556 | - | 0.474 | {'task_fail': 3} |
| migration-shipments-assets | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.571 | 0.556 | - | 2.58 | {'task_fail': 3} |
| migration-shipments-assets | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.857 | 0.444 | {'migrating-to-airflow-3': 3} | 0.809 | {'task_fail': 2, 'turn_limit': 1} |
| migration-shipments-assets | migration | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.857 | 1 | {'migrating-to-airflow-3': 3} | 2.62 | {'turn_limit': 1, 'task_fail': 2} |
| scheduling-backfill-pageviews | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.407 | 0.667 | - | 0.54 | {'task_fail': 3} |
| scheduling-backfill-pageviews | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.778 | 0.667 | - | 1.12 | {'task_fail': 3} |
| scheduling-backfill-pageviews | scheduling | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.63 | 0.889 | {'authoring-airflow-dags': 2} | 0.555 | {'task_fail': 2, 'ok': 1} |
| scheduling-backfill-pageviews | scheduling | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 1.88 | {'ok': 3} |
| testing-taskflow-transforms | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.542 | 1 | - | 0.767 | {'task_fail': 3} |
| testing-taskflow-transforms | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 33% | 0.917 | 1 | - | 2.12 | {'task_fail': 2, 'ok': 1} |
| testing-taskflow-transforms | testing | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.25 | 0.917 | {'testing-airflow-dags': 2} | 0.931 | {'turn_limit': 3} |
| testing-taskflow-transforms | testing | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'testing-airflow-dags': 3} | 2.6 | {'ok': 3} |

## Failure classes (all runs)

{'ok': 138, 'task_fail': 78, 'turn_limit': 23, 'cost_limit': 1}

Total spend (all attempts, all dirs): $306.97

## Isolation

Contamination suspects: 97 run(s).
- authoring-daily-revenue-yesterday baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: read:<work>/baseline-2026-09-30-baseline-20260930-yesterday-pyn34e58/ws/README.md (work-root), bash:<tmp>/first_run.csv (shared-temp), bash:<tmp>/second_run.csv (shared-temp), bash:<tmp>/first_run.csv (shared-temp), bash:<tmp>/second_run.csv (shared-temp)
- debugging-manual-trigger-context baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/fix_summary.md (shared-temp), bash:<tmp>/fix_summary.md (shared-temp), bash:<tmp>/partner_feed_before.py (shared-temp), bash:<tmp>/partner_feed_after.py (shared-temp), bash:<tmp>/partner_feed_before.py (shared-temp)
- authoring-vendor-shipments-etl baseline google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/airflow-test- (shared-temp), bash:///<tmp>/airflow-test- (shared-temp)
- authoring-vendor-shipments-etl baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/vendor_shipments_verification.md (shared-temp), bash:<tmp>/vendor_shipments_verification.md (shared-temp)
- debugging-nondeterministic-parse baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/warehouse_ingest_fix_summary.md (shared-temp), bash:<tmp>/warehouse_ingest_fix_summary.md (shared-temp)
- debugging-variable-at-parse baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/warehouse (shared-temp), bash:<tmp>/fix_summary.md (shared-temp), bash:<tmp>/fix_summary.md (shared-temp)
- migration-hourly-pageviews-templates baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/migration_summary.md (shared-temp), bash:<tmp>/migration_summary.md (shared-temp), bash:<tmp>/detailed_changes.md (shared-temp), bash:<tmp>/detailed_changes.md (shared-temp)
- migration-inventory-context baseline google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/inv_test (shared-temp)
- migration-shipments-assets baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/migration_summary.txt (shared-temp), bash:<tmp>/migration_summary.txt (shared-temp)
- migration-revenue-previous-day baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: read:<work>/baseline-2026-09-30-baseline-20260930-45309/migration-revenue-previous-day-hfc9t_wx/ws/dags/sql/daily_revenue.sql (work-root), read:<work>/baseline-2026-09-30-baseline-20260930-45309/migration-revenue-previous-day-hfc9t_wx/ws/data/orders.csv (work-root), bash:<tmp>/migration_summary.md (shared-temp), bash:<tmp>/migration_summary.md (shared-temp), bash:<tmp>/MIGRATION_CHECKLIST.md (shared-temp)
- migration-weekly-catchup baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/migration_summary.md (shared-temp), bash:<tmp>/migration_summary.md (shared-temp)
- scheduling-weekday-ny-business-day baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/CHANGES_SUMMARY.md (shared-temp), bash:<tmp>/CHANGES_SUMMARY.md (shared-temp), bash:<tmp>/SCHEDULE_DIAGRAM.txt (shared-temp), bash:<tmp>/SCHEDULE_DIAGRAM.txt (shared-temp)
- scheduling-idempotent-orders-load baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/fix_summary.md (shared-temp), bash:<tmp>/fix_summary.md (shared-temp), bash:<tmp>/CHANGES.txt (shared-temp), bash:<tmp>/CHANGES.txt (shared-temp)
- testing-airflow2-ci-suite baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/analyze_shipments.py (shared-temp), bash:<tmp>/analyze_shipments.py (shared-temp), bash:<tmp>/test_summary.txt (shared-temp), bash:<tmp>/test_summary.txt (shared-temp)
- testing-custom-operator-conn baseline google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/test.db (shared-temp), bash:<tmp>/test.db (shared-temp), bash:<tmp>/test.db (shared-temp), bash:<tmp>/testdb.duckdb (shared-temp), bash:<tmp>/testdb.duckdb (shared-temp)
- testing-custom-operator-conn baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: write:<work>/baseline-2026-09-30-baseline-20260930-baseline-20260930-045309/testing-custom-operator-conn-z5v0yj2h/ws/conftest.py (work-root), bash:<work>/baseline-2026-09-30-baseline-20260930-baseline-20260930-045309/testing-custom-operator-conn-z5v0yj2h/ws/conftest.py (work-root)
- authoring-daily-revenue-yesterday baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/summary.txt (shared-temp), bash:<tmp>/summary.txt (shared-temp)
- authoring-vendor-shipments-etl baseline google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/landing (shared-temp)
- debugging-manual-trigger-context baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/fix_summary.md (shared-temp), bash:<tmp>/fix_summary.md (shared-temp)
- authoring-vendor-shipments-etl baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/vendor_shipments_summary.md (shared-temp), bash:<tmp>/vendor_shipments_summary.md (shared-temp)
- debugging-variable-at-parse baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: read:<work>/baseline-2026-09-30-baseline-20260930-baseline-20260930-045309/debugging-variable-at-parse-y19jdpne/ws/dags/warehouse_load.py (work-root)
- debugging-nondeterministic-parse baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/warehouse_ingest_fix_summary.md (shared-temp), bash:<tmp>/warehouse_ingest_fix_summary.md (shared-temp), bash:<tmp>/before_after.txt (shared-temp), bash:<tmp>/before_after.txt (shared-temp)
- migration-hourly-pageviews-templates baseline google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp> (shared-temp)
- migration-shipments-assets baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/migration_summary.txt (shared-temp), bash:<tmp>/migration_summary.txt (shared-temp), bash:<tmp>/verification.txt (shared-temp), bash:<tmp>/verification.txt (shared-temp)
- scheduling-idempotent-orders-load baseline google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/airflow-test- (shared-temp), bash:<tmp>/airflow-test-idempotent (shared-temp), bash:<tmp>/airflow-test-idempotent (shared-temp), bash:<tmp>/airflow-test-idempotent (shared-temp), bash:<tmp>/airflow-test-idempotent (shared-temp)
- testing-custom-operator-conn baseline google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/test.duckdb (shared-temp)
- authoring-clickstream-claim-check baseline google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test2 (shared-temp), bash:<tmp>/airflow_test2 (shared-temp), bash:<tmp>/airflow_test2 (shared-temp)
- authoring-clickstream-claim-check baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/dag_summary.txt (shared-temp), bash:<tmp>/dag_summary.txt (shared-temp)
- authoring-daily-revenue-yesterday baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<work>/baseline-run3-2026-09-30-baseline-20260930-baseline-20260930-082417/authoring-daily-revenue-yesterday-ew4q6g1i/ws (work-root)
- authoring-vendor-shipments-etl baseline google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/landing (shared-temp)
- authoring-vendor-shipments-etl baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp)
- debugging-manual-trigger-context baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: read:<work>/baseline-run3-2026-09-30-baseline-20260930-baseline-20260930-082417/debugging-manual-trigger-context-1x63tzof/ws/dags/partner_feed.py (work-root)
- debugging-nondeterministic-parse baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/fix_summary.md (shared-temp), bash:<tmp>/fix_summary.md (shared-temp)
- debugging-variable-at-parse baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: edit:<work>/baseline-run3-2026-09-30-baseline-20260930-debugging-variable-at-parse-ldmu9aj0/ws/dags/warehouse_load.py (work-root), bash:<work>/baseline-run3-2026-09-30-baseline-20260930-082417 (work-root), bash:<tmp>/airflow_fix_summary.md (shared-temp), bash:<tmp>/airflow_fix_summary.md (shared-temp)
- migration-inventory-context baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/upgrade_summary.md (shared-temp), bash:<tmp>/upgrade_summary.md (shared-temp), bash:<work>/baseline-run3-2026-09-30-baseline-20260930-182417/migration-inventory-context-im02tn8a/ws/dags/inventory_snapshot.py (work-root)
- migration-shipments-assets baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: read:<work>/baseline-run3-2026-09-30-baseline-20260930-baseline-20260930-082417/migration-shipments-assets-bz1624jc/ws/dags/carrier_scorecard.py (work-root)
- scheduling-backfill-pageviews baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/pageviews_setup_summary.md (shared-temp), bash:<tmp>/pageviews_setup_summary.md (shared-temp), bash:<tmp>/test_pageviews_idempotency.py (shared-temp), bash:<tmp>/test_pageviews_idempotency.py (shared-temp), bash:<tmp>/CHANGES.md (shared-temp)
- scheduling-idempotent-orders-load baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/dag_fix_summary.md (shared-temp), bash:<tmp>/dag_fix_summary.md (shared-temp)
- scheduling-weekday-ny-business-day baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/fx_pnl_changes_summary.md (shared-temp), bash:<tmp>/fx_pnl_changes_summary.md (shared-temp)
- testing-custom-operator-conn baseline google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/test.duckdb (shared-temp)
- testing-taskflow-transforms baseline google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp)
- authoring-clickstream-claim-check skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test_csp (shared-temp), bash:<tmp>/airflow_test_csp (shared-temp), bash:<tmp>/airflow_test_csp (shared-temp)
- authoring-daily-revenue-yesterday skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test_dr (shared-temp), bash:<tmp>/airflow_test_dr (shared-temp), bash:<tmp>/airflow_test_dr2 (shared-temp), bash:<tmp>/airflow_test_dr2 (shared-temp)
- debugging-manual-trigger-context skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- authoring-vendor-shipments-etl skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/vendor_shipments_summary.md (shared-temp), bash:<tmp>/vendor_shipments_summary.md (shared-temp), bash:<tmp>/deployment_guide.md (shared-temp), bash:<tmp>/deployment_guide.md (shared-temp)
- authoring-vendor-shipments-etl skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:///<tmp>/airflow_vendor_test_ (shared-temp), bash:<tmp>/airflow_vendor_home_ (shared-temp), bash:///<tmp>/airflow_vendor_test2_ (shared-temp), bash:<tmp>/airflow_vendor_home2_ (shared-temp), bash:///<tmp>/airflow_vendor_test2_ (shared-temp)
- debugging-variable-at-parse skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/test_warehouse (shared-temp)
- debugging-variable-at-parse skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-hourly-pageviews-templates skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- migration-hourly-pageviews-templates skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-inventory-context skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/before.json (shared-temp)
- migration-inventory-context skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- migration-revenue-previous-day skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- migration-shipments-assets skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-shipments-assets skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/migration_notes.md (shared-temp), bash:<tmp>/migration_notes.md (shared-temp), bash:<tmp>/before_baseline.txt (shared-temp), bash:<tmp>/before_baseline.txt (shared-temp), bash:<tmp>/after_verification.txt (shared-temp)
- migration-weekly-catchup skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-weekly-catchup skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- scheduling-backfill-pageviews skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/airflow_test_pv_ (shared-temp), bash:<tmp>/airflow_test_pv_ (shared-temp), bash:<tmp>/airflow_test_pv2 (shared-temp), bash:<tmp>/airflow_test_pv2 (shared-temp), bash:<tmp>/airflow_test_pv2 (shared-temp)
- scheduling-weekday-ny-business-day skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/af_test_ (shared-temp)
- testing-custom-operator-conn skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/test_airflow (shared-temp)
- authoring-clickstream-claim-check skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test_1 (shared-temp), bash:<tmp>/af_test_ (shared-temp), bash:<tmp>/first_run_2026-09-27.csv (shared-temp)
- authoring-partner-feeds-mapping skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/test_dag.py (shared-temp), bash:<tmp>/test_dag.py (shared-temp), bash:<tmp>/verify_dag_structure.py (shared-temp), bash:<tmp>/verify_dag_structure.py (shared-temp), bash:<tmp>/verify_dag_structure.py (shared-temp)
- authoring-vendor-shipments-etl skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp><tmp>.nymKSGkNb1 (shared-temp), bash:<tmp>/ (shared-temp)
- debugging-manual-trigger-context skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/test_summary.md (shared-temp), bash:<tmp>/test_summary.md (shared-temp)
- debugging-variable-at-parse skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/before.json (shared-temp)
- debugging-nondeterministic-parse skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/warehouse_ingest_fix_summary.md (shared-temp), bash:<tmp>/warehouse_ingest_fix_summary.md (shared-temp)
- authoring-vendor-shipments-etl skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/vendor_shipments_summary.md (shared-temp), bash:<tmp>/vendor_shipments_summary.md (shared-temp), bash:<tmp>/requirements_checklist.txt (shared-temp), bash:<tmp>/requirements_checklist.txt (shared-temp), bash:<tmp>/usage_guide.md (shared-temp)
- migration-hourly-pageviews-templates skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-hourly-pageviews-templates skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- migration-inventory-context skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- migration-inventory-context skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-revenue-previous-day skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-revenue-previous-day skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- migration-shipments-assets skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-shipments-assets skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/after.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-weekly-catchup skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- scheduling-backfill-pageviews skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/af_test_pv_ (shared-temp), bash:<tmp>/af_test_pv_ (shared-temp), bash:<tmp>/af_test_pv_ (shared-temp), bash:<tmp>/af_test_pv2 (shared-temp), bash:<tmp>/af_test_pv2 (shared-temp)
- scheduling-idempotent-orders-load skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/verification_summary.txt (shared-temp), bash:<tmp>/verification_summary.txt (shared-temp)
- scheduling-idempotent-orders-load skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/test_dag.sh (shared-temp), bash:<tmp>/test_dag.sh (shared-temp), bash:<tmp>/test_dag.sh (shared-temp), bash:<tmp>/test_dag.sh (shared-temp), bash:<tmp>/test_dag.sh (shared-temp)
- migration-weekly-catchup skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- authoring-airflow2-inventory-snapshot skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test_inv (shared-temp), bash:<tmp>/airflow_inv2 (shared-temp), bash:<tmp>/airflow_inv2 (shared-temp)
- authoring-clickstream-claim-check skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/first_run_2026-09-29.csv (shared-temp), bash:<tmp>/first_run_2026-09-29.csv (shared-temp)
- testing-taskflow-transforms skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/orders_enrichment.py.bak (shared-temp), bash:<tmp>/orders_enrichment.py.bak (shared-temp), bash:<tmp>/orders_enrichment.py.bak (shared-temp), bash:<tmp>/orders_enrichment.py.bak (shared-temp), bash:<tmp>/orders_enrichment.py.bak (shared-temp)
- debugging-variable-at-parse skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/before.json (shared-temp)
- debugging-variable-at-parse skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/test_warehouse (shared-temp), bash:<tmp>/fix_summary.md (shared-temp), bash:<tmp>/fix_summary.md (shared-temp), bash:<tmp>/ci_warehouse (shared-temp), bash:<tmp>/ci_warehouse/warehouse.duckdb (shared-temp)
- migration-hourly-pageviews-templates skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-hourly-pageviews-templates skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- migration-inventory-context skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-revenue-previous-day skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- migration-revenue-previous-day skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/migration_summary.txt (shared-temp), bash:<tmp>/migration_summary.txt (shared-temp)
- migration-shipments-assets skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-weekly-catchup skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-weekly-catchup skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- scheduling-backfill-pageviews skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/af_test_ (shared-temp), bash:<tmp>/af_test_ (shared-temp), bash:<tmp>/af_test2_ (shared-temp), bash:<tmp>/af_test2_ (shared-temp), bash:<tmp>/af_test2_ (shared-temp)
- scheduling-backfill-pageviews skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/test_pageviews_backfill.py (shared-temp), bash:<tmp>/test_pageviews_backfill.py (shared-temp), bash:<tmp>/BACKFILL_SETUP_SUMMARY.md (shared-temp), bash:<tmp>/BACKFILL_SETUP_SUMMARY.md (shared-temp), bash:<tmp>/test_idempotency.py (shared-temp)
- scheduling-idempotent-orders-load skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp><tmp>.IKuqtA2Qn0 (shared-temp), bash:<tmp><tmp>.IKuqtA2Qn0 (shared-temp), bash:<tmp><tmp>.IKuqtA2Qn0 (shared-temp)
- testing-custom-operator-conn skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/test.duckdb (shared-temp)
Broad kill commands (pkill/killall/kill by pattern): 0 run(s). None.
Agent env restored after: 0 run(s); restore failed: 0.

## Sources

- `evals/airflow/results/baseline-2026-09-30`: arm=None models=None altimate-code=None started=None budget=None
- `evals/airflow/results/baseline-run3-2026-09-30`: arm=None models=None altimate-code=None started=None budget=None
- `evals/airflow/results/skill-2026-09-30`: arm=None models=None altimate-code=None started=None budget=None
