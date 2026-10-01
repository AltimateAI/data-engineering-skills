# Airflow skill eval report

Pass rate = fraction of valid runs whose primary checks all passed. Excluded runs (infra_error, grader_error, skipped_budget) are listed but not counted.

## dev: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 38 (38) | 34% | 0.655 | 0.695 | 0% | 3.93e+06 | 0.648 | 190 | {'ok': 13, 'task_fail': 18, 'turn_limit': 7} |
| baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 37 (37) | 54% | 0.796 | 0.712 | 0% | 2.8e+06 | 1.45 | 169 | {'ok': 20, 'task_fail': 12, 'turn_limit': 5} |
| skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 36 (36) | 81% | 0.925 | 0.917 | 92% | 3.79e+06 | 0.642 | 159 | {'ok': 29, 'task_fail': 6, 'turn_limit': 1} |
| skill | google-vertex-anthropic/claude-sonnet-4-6@default | 33 (33) | 94% | 0.991 | 0.929 | 100% | 3.48e+06 | 1.83 | 175 | {'ok': 31, 'task_fail': 2} |

## dev: paired delta (skill - baseline) over cases

| model | cases | delta pass rate | 95% CI | delta primary score | 95% CI |
|---|---|---|---|---|---|
| google-vertex-anthropic/claude-haiku-4-5@20251001 | 13 | 0.462 | (0.2051, 0.6923) | 0.266 | (0.0855, 0.4491) |
| google-vertex-anthropic/claude-sonnet-4-6@default | 12 | 0.333 | (0.1111, 0.5833) | 0.182 | (0.0571, 0.3608) |
| pooled (25 case x model pairs) | 13 | 0.4 | (0.2, 0.6061) | 0.226 | (0.1013, 0.3483) |

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
| authoring-vendor-shipments-etl | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 100% | 1 | 0.5 | - | 1.43 | {'ok': 2} |
| authoring-vendor-shipments-etl | authoring | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.861 | 0.778 | {'authoring-airflow-dags': 1} | 0.704 | {'ok': 1, 'task_fail': 2} |
| authoring-vendor-shipments-etl | authoring | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.667 | {'authoring-airflow-dags': 3} | 2.29 | {'ok': 3} |
| debugging-manual-trigger-context | debugging | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.714 | 0.667 | - | 0.392 | {'task_fail': 3} |
| debugging-manual-trigger-context | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.762 | 0.667 | - | 0.816 | {'task_fail': 3} |
| debugging-manual-trigger-context | debugging | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.905 | 0.889 | {'migrating-to-airflow-3': 3} | 0.607 | {'task_fail': 1, 'ok': 2} |
| debugging-manual-trigger-context | debugging | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 33% | 0.905 | 0.778 | {'migrating-to-airflow-3': 3} | 1.52 | {'task_fail': 2, 'ok': 1} |
| debugging-variable-at-parse | debugging | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 100% | 1 | 0.833 | - | 0.444 | {'ok': 2} |
| debugging-variable-at-parse | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0 | 0.333 | - | 1 | {'task_fail': 3} |
| debugging-variable-at-parse | debugging | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 100% | 1 | 1 | {'migrating-to-airflow-3': 2} | 0.375 | {'ok': 2} |
| debugging-variable-at-parse | debugging | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 100% | 1 | 0.667 | {'migrating-to-airflow-3': 2} | 0.82 | {'ok': 2} |
| migration-inventory-context | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.533 | 0.222 | - | 0.572 | {'task_fail': 3} |
| migration-inventory-context | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.8 | 0.444 | - | 1.48 | {'task_fail': 3} |
| migration-inventory-context | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 0.667 | {'migrating-to-airflow-3': 3} | 0.699 | {'ok': 3} |
| migration-inventory-context | migration | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 100% | 1 | 1 | {'migrating-to-airflow-3': 2} | 2.23 | {'ok': 2} |
| migration-revenue-previous-day | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.476 | 0.667 | - | 0.755 | {'turn_limit': 3} |
| migration-revenue-previous-day | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.762 | 0.667 | - | 2.41 | {'turn_limit': 2, 'task_fail': 1} |
| migration-revenue-previous-day | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 0.667 | {'migrating-to-airflow-3': 3} | 0.682 | {'ok': 3} |
| migration-weekly-catchup | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.333 | 0.333 | - | 0.827 | {'task_fail': 2, 'turn_limit': 1} |
| migration-weekly-catchup | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.714 | 0.778 | - | 2.74 | {'turn_limit': 3} |
| migration-weekly-catchup | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 1 | {'migrating-to-airflow-3': 3} | 0.728 | {'ok': 3} |
| migration-weekly-catchup | migration | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 100% | 1 | 1 | {'migrating-to-airflow-3': 2} | 2.65 | {'ok': 2} |
| scheduling-idempotent-orders-load | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.611 | 0.889 | - | 0.778 | {'task_fail': 2, 'ok': 1} |
| scheduling-idempotent-orders-load | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 67% | 0.778 | 0.778 | - | 0.993 | {'task_fail': 1, 'ok': 2} |
| scheduling-idempotent-orders-load | scheduling | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 100% | 1 | 1 | {'authoring-airflow-dags': 2} | 0.602 | {'ok': 2} |
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
| testing-custom-operator-conn | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 100% | 1 | 1 | - | 1.74 | {'ok': 2} |
| testing-custom-operator-conn | testing | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 100% | 1 | 1 | {'testing-airflow-dags': 2} | 0.663 | {'ok': 2} |
| testing-custom-operator-conn | testing | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'testing-airflow-dags': 3} | 1.56 | {'ok': 3} |
| testing-dagbag-integrity | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.708 | 0.75 | - | 0.73 | {'turn_limit': 1, 'ok': 2} |
| testing-dagbag-integrity | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | - | 1.31 | {'ok': 3} |
| testing-dagbag-integrity | testing | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.958 | 1 | {'testing-airflow-dags': 2} | 0.597 | {'task_fail': 1, 'ok': 2} |
| testing-dagbag-integrity | testing | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'testing-airflow-dags': 3} | 1.45 | {'ok': 3} |

## holdout: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 20 (20) | 20% | 0.552 | 0.717 | 0% | 3.8e+06 | 0.676 | 200 | {'ok': 4, 'turn_limit': 2, 'task_fail': 14} |
| baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 20 (20) | 35% | 0.792 | 0.65 | 0% | 2.94e+06 | 1.83 | 194 | {'ok': 7, 'task_fail': 12, 'cost_limit': 1} |
| skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 19 (19) | 26% | 0.679 | 0.829 | 79% | 4.47e+06 | 0.826 | 185 | {'ok': 5, 'task_fail': 8, 'turn_limit': 6} |
| skill | google-vertex-anthropic/claude-sonnet-4-6@default | 18 (18) | 78% | 0.971 | 0.963 | 100% | 3.98e+06 | 2.47 | 245 | {'ok': 14, 'turn_limit': 1, 'task_fail': 3} |

## holdout: paired delta (skill - baseline) over cases

| model | cases | delta pass rate | 95% CI | delta primary score | 95% CI |
|---|---|---|---|---|---|
| google-vertex-anthropic/claude-haiku-4-5@20251001 | 7 | 0.0476 | (0.0, 0.1428) | 0.0868 | (-0.1295, 0.3647) |
| google-vertex-anthropic/claude-sonnet-4-6@default | 6 | 0.389 | (0.0, 0.7778) | 0.137 | (0.0412, 0.2275) |
| pooled (13 case x model pairs) | 7 | 0.205 | (0.0, 0.4286) | 0.11 | (-0.0266, 0.2822) |

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
| migration-hourly-pageviews-templates | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 1 (1) | 0% | 0.286 | 0.667 | {'migrating-to-airflow-3': 1} | 0.819 | {'task_fail': 1} |
| migration-shipments-assets | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0 | 0.556 | - | 0.474 | {'task_fail': 3} |
| migration-shipments-assets | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.571 | 0.556 | - | 2.58 | {'task_fail': 3} |
| migration-shipments-assets | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.857 | 0.444 | {'migrating-to-airflow-3': 3} | 0.809 | {'task_fail': 2, 'turn_limit': 1} |
| migration-shipments-assets | migration | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.857 | 1 | {'migrating-to-airflow-3': 3} | 2.62 | {'turn_limit': 1, 'task_fail': 2} |
| scheduling-backfill-pageviews | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 0% | 0.611 | 0.667 | - | 0.395 | {'task_fail': 2} |
| scheduling-backfill-pageviews | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.778 | 0.667 | - | 1.12 | {'task_fail': 3} |
| scheduling-backfill-pageviews | scheduling | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 33% | 0.63 | 0.889 | {'authoring-airflow-dags': 2} | 0.555 | {'task_fail': 2, 'ok': 1} |
| scheduling-backfill-pageviews | scheduling | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 1.88 | {'ok': 3} |
| testing-taskflow-transforms | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.542 | 1 | - | 0.767 | {'task_fail': 3} |
| testing-taskflow-transforms | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 0% | 0.875 | 1 | - | 1.7 | {'task_fail': 2} |
| testing-taskflow-transforms | testing | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.25 | 0.917 | {'testing-airflow-dags': 2} | 0.931 | {'turn_limit': 3} |
| testing-taskflow-transforms | testing | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'testing-airflow-dags': 3} | 2.6 | {'ok': 3} |

## Failure classes (all runs)

{'ok': 123, 'task_fail': 75, 'turn_limit': 22, 'cost_limit': 1}

Total spend (all attempts, all dirs): $271.86

## Isolation

Contamination suspects: 78 run(s).
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
- authoring-vendor-shipments-etl baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp), bash:<tmp>/airflow_test (shared-temp)
- debugging-manual-trigger-context baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: read:<work>/baseline-run3-2026-09-30-baseline-20260930-baseline-20260930-082417/debugging-manual-trigger-context-1x63tzof/ws/dags/partner_feed.py (work-root)
- debugging-nondeterministic-parse baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/fix_summary.md (shared-temp), bash:<tmp>/fix_summary.md (shared-temp)
- migration-inventory-context baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/upgrade_summary.md (shared-temp), bash:<tmp>/upgrade_summary.md (shared-temp), bash:<work>/baseline-run3-2026-09-30-baseline-20260930-182417/migration-inventory-context-im02tn8a/ws/dags/inventory_snapshot.py (work-root)
- migration-shipments-assets baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: read:<work>/baseline-run3-2026-09-30-baseline-20260930-baseline-20260930-082417/migration-shipments-assets-bz1624jc/ws/dags/carrier_scorecard.py (work-root)
- scheduling-idempotent-orders-load baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/dag_fix_summary.md (shared-temp), bash:<tmp>/dag_fix_summary.md (shared-temp)
- scheduling-weekday-ny-business-day baseline google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/fx_pnl_changes_summary.md (shared-temp), bash:<tmp>/fx_pnl_changes_summary.md (shared-temp)
- authoring-clickstream-claim-check skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test_csp (shared-temp), bash:<tmp>/airflow_test_csp (shared-temp), bash:<tmp>/airflow_test_csp (shared-temp)
- authoring-daily-revenue-yesterday skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test_dr (shared-temp), bash:<tmp>/airflow_test_dr (shared-temp), bash:<tmp>/airflow_test_dr2 (shared-temp), bash:<tmp>/airflow_test_dr2 (shared-temp)
- debugging-manual-trigger-context skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- authoring-vendor-shipments-etl skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/vendor_shipments_summary.md (shared-temp), bash:<tmp>/vendor_shipments_summary.md (shared-temp), bash:<tmp>/deployment_guide.md (shared-temp), bash:<tmp>/deployment_guide.md (shared-temp)
- authoring-vendor-shipments-etl skill google-vertex-anthropic/claude-sonnet-4-6@default run 1: bash:///<tmp>/airflow_vendor_test_ (shared-temp), bash:<tmp>/airflow_vendor_home_ (shared-temp), bash:///<tmp>/airflow_vendor_test2_ (shared-temp), bash:<tmp>/airflow_vendor_home2_ (shared-temp), bash:///<tmp>/airflow_vendor_test2_ (shared-temp)
- debugging-variable-at-parse skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/test_warehouse (shared-temp)
- migration-hourly-pageviews-templates skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- migration-inventory-context skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 1: bash:<tmp>/before.json (shared-temp)
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
- migration-inventory-context skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- migration-inventory-context skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-revenue-previous-day skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-shipments-assets skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-shipments-assets skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/after.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-weekly-catchup skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp)
- scheduling-backfill-pageviews skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/af_test_pv_ (shared-temp), bash:<tmp>/af_test_pv_ (shared-temp), bash:<tmp>/af_test_pv_ (shared-temp), bash:<tmp>/af_test_pv2 (shared-temp), bash:<tmp>/af_test_pv2 (shared-temp)
- scheduling-idempotent-orders-load skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/test_dag.sh (shared-temp), bash:<tmp>/test_dag.sh (shared-temp), bash:<tmp>/test_dag.sh (shared-temp), bash:<tmp>/test_dag.sh (shared-temp), bash:<tmp>/test_dag.sh (shared-temp)
- migration-weekly-catchup skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 2: bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- authoring-airflow2-inventory-snapshot skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test_ (shared-temp), bash:<tmp>/airflow_test_inv (shared-temp), bash:<tmp>/airflow_inv2 (shared-temp), bash:<tmp>/airflow_inv2 (shared-temp)
- authoring-clickstream-claim-check skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/first_run_2026-09-29.csv (shared-temp), bash:<tmp>/first_run_2026-09-29.csv (shared-temp)
- testing-taskflow-transforms skill google-vertex-anthropic/claude-sonnet-4-6@default run 2: bash:<tmp>/orders_enrichment.py.bak (shared-temp), bash:<tmp>/orders_enrichment.py.bak (shared-temp), bash:<tmp>/orders_enrichment.py.bak (shared-temp), bash:<tmp>/orders_enrichment.py.bak (shared-temp), bash:<tmp>/orders_enrichment.py.bak (shared-temp)
- debugging-variable-at-parse skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/before.json (shared-temp)
- migration-inventory-context skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-revenue-previous-day skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/migration_summary.txt (shared-temp), bash:<tmp>/migration_summary.txt (shared-temp)
- migration-shipments-assets skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/before.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- migration-weekly-catchup skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp), bash:<tmp>/before.json (shared-temp), bash:<tmp>/after.json (shared-temp)
- scheduling-backfill-pageviews skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp>/af_test_ (shared-temp), bash:<tmp>/af_test_ (shared-temp), bash:<tmp>/af_test2_ (shared-temp), bash:<tmp>/af_test2_ (shared-temp), bash:<tmp>/af_test2_ (shared-temp)
- scheduling-backfill-pageviews skill google-vertex-anthropic/claude-haiku-4-5@20251001 run 3: bash:<tmp>/test_pageviews_backfill.py (shared-temp), bash:<tmp>/test_pageviews_backfill.py (shared-temp), bash:<tmp>/BACKFILL_SETUP_SUMMARY.md (shared-temp), bash:<tmp>/BACKFILL_SETUP_SUMMARY.md (shared-temp), bash:<tmp>/test_idempotency.py (shared-temp)
- scheduling-idempotent-orders-load skill google-vertex-anthropic/claude-sonnet-4-6@default run 3: bash:<tmp><tmp>.IKuqtA2Qn0 (shared-temp), bash:<tmp><tmp>.IKuqtA2Qn0 (shared-temp), bash:<tmp><tmp>.IKuqtA2Qn0 (shared-temp)
Broad kill commands (pkill/killall/kill by pattern): 0 run(s). None.
Agent env restored after: 0 run(s); restore failed: 0.

## Sources

- `evals/airflow/results/baseline-2026-09-30`: arm=None models=None altimate-code=None started=None budget=None
- `evals/airflow/results/baseline-run3-2026-09-30`: arm=None models=None altimate-code=None started=None budget=None
- `evals/airflow/results/skill-2026-09-30`: arm=None models=None altimate-code=None started=None budget=None
