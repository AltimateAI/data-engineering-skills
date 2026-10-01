# Airflow skill eval report

Pass rate = fraction of valid runs whose primary checks all passed. Excluded runs (infra_error, grader_error, skipped_budget) are listed but not counted.

## dev: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 20 (20) | 40% | 0.636 | 0.654 | 0% | 4.07e+06 | 0.645 | 203 | {'ok': 8, 'task_fail': 7, 'turn_limit': 5} |
| baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 30 (30) | 47% | 0.755 | 0.689 | 0% | 2.74e+06 | 1.42 | 164 | {'ok': 14, 'task_fail': 11, 'turn_limit': 5} |
| skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 24 (24) | 75% | 0.901 | 0.958 | 96% | 3.6e+06 | 0.632 | 156 | {'ok': 18, 'task_fail': 5, 'turn_limit': 1} |
| skill | google-vertex-anthropic/claude-sonnet-4-6@default | 17 (17) | 94% | 0.992 | 0.961 | 100% | 2.9e+06 | 1.58 | 151 | {'ok': 16, 'task_fail': 1} |

## dev: paired delta (skill - baseline) over cases

| model | cases | delta pass rate | 95% CI | delta primary score | 95% CI |
|---|---|---|---|---|---|
| google-vertex-anthropic/claude-haiku-4-5@20251001 | 9 | 0.426 | (0.0926, 0.7778) | 0.267 | (0.0299, 0.5093) |
| google-vertex-anthropic/claude-sonnet-4-6@default | 6 | 0.222 | (0.0555, 0.3889) | 0.139 | (0.0278, 0.25) |
| pooled (15 case x model pairs) | 10 | 0.344 | (0.1146, 0.6333) | 0.215 | (0.0536, 0.4125) |

Pooled CI: bootstrap over cases; a resampled case carries the deltas of all its models.

## dev: per case

| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| authoring-airflow2-inventory-snapshot | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.857 | 0.667 | - | 0.35 | {'ok': 2, 'task_fail': 1} |
| authoring-airflow2-inventory-snapshot | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.667 | - | 0.722 | {'ok': 3} |
| authoring-airflow2-inventory-snapshot | authoring | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.857 | 1 | {'authoring-airflow-dags': 3} | 0.691 | {'ok': 2, 'task_fail': 1} |
| authoring-airflow2-inventory-snapshot | authoring | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 100% | 1 | 1 | {'authoring-airflow-dags': 2} | 1.47 | {'ok': 2} |
| authoring-clickstream-claim-check | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 50% | 0.929 | 0.833 | - | 0.571 | {'task_fail': 1, 'ok': 1} |
| authoring-clickstream-claim-check | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 100% | 1 | 0.667 | - | 1.25 | {'ok': 2} |
| authoring-clickstream-claim-check | authoring | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.809 | 1 | {'authoring-airflow-dags': 3} | 0.645 | {'ok': 2, 'task_fail': 1} |
| authoring-vendor-shipments-etl | authoring | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 1 (1) | 0% | 0.917 | 1 | {'authoring-airflow-dags': 1} | 0.854 | {'task_fail': 1} |
| authoring-vendor-shipments-etl | authoring | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 1 (1) | 100% | 1 | 0.667 | {'authoring-airflow-dags': 1} | 1.37 | {'ok': 1} |
| debugging-manual-trigger-context | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.762 | 0.667 | - | 0.816 | {'task_fail': 3} |
| debugging-manual-trigger-context | debugging | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 50% | 0.857 | 0.833 | {'migrating-to-airflow-3': 2} | 0.589 | {'task_fail': 1, 'ok': 1} |
| debugging-manual-trigger-context | debugging | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 50% | 0.929 | 0.833 | {'migrating-to-airflow-3': 2} | 1.27 | {'task_fail': 1, 'ok': 1} |
| debugging-variable-at-parse | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0 | 0.333 | - | 1 | {'task_fail': 3} |
| debugging-variable-at-parse | debugging | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 1 (1) | 100% | 1 | 1 | {'migrating-to-airflow-3': 1} | 0.322 | {'ok': 1} |
| migration-inventory-context | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 0% | 0.6 | 0.167 | - | 0.46 | {'task_fail': 2} |
| migration-inventory-context | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 0% | 0.8 | 0.333 | - | 1.53 | {'task_fail': 2} |
| migration-inventory-context | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 1 (1) | 100% | 1 | 0.667 | {'migrating-to-airflow-3': 1} | 0.559 | {'ok': 1} |
| migration-revenue-previous-day | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 0% | 0.429 | 0.667 | - | 0.765 | {'turn_limit': 2} |
| migration-revenue-previous-day | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.762 | 0.667 | - | 2.41 | {'turn_limit': 2, 'task_fail': 1} |
| migration-revenue-previous-day | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 1 (1) | 100% | 1 | 0.667 | {'migrating-to-airflow-3': 1} | 0.847 | {'ok': 1} |
| migration-weekly-catchup | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 0% | 0.286 | 0.333 | - | 0.835 | {'task_fail': 1, 'turn_limit': 1} |
| migration-weekly-catchup | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.714 | 0.778 | - | 2.74 | {'turn_limit': 3} |
| scheduling-idempotent-orders-load | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 1 (1) | 100% | 1 | 0.667 | - | 0.917 | {'ok': 1} |
| scheduling-idempotent-orders-load | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 50% | 0.667 | 0.667 | - | 0.759 | {'task_fail': 1, 'ok': 1} |
| scheduling-idempotent-orders-load | scheduling | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 100% | 1 | 1 | {'authoring-airflow-dags': 2} | 0.602 | {'ok': 2} |
| scheduling-idempotent-orders-load | scheduling | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 1.81 | {'ok': 1} |
| scheduling-weekday-ny-business-day | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 1 (1) | 0% | 0.286 | 0.667 | - | 0.665 | {'task_fail': 1} |
| scheduling-weekday-ny-business-day | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 67% | 0.667 | 0.667 | - | 0.844 | {'ok': 2, 'task_fail': 1} |
| scheduling-weekday-ny-business-day | scheduling | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 0.37 | {'ok': 3} |
| scheduling-weekday-ny-business-day | scheduling | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 100% | 1 | 1 | {'authoring-airflow-dags': 2} | 1.22 | {'ok': 2} |
| testing-airflow2-ci-suite | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 100% | 1 | 1 | - | 0.728 | {'ok': 2} |
| testing-airflow2-ci-suite | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | - | 2.04 | {'ok': 3} |
| testing-airflow2-ci-suite | testing | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.708 | 1 | {'testing-airflow-dags': 3} | 0.891 | {'turn_limit': 1, 'ok': 2} |
| testing-airflow2-ci-suite | testing | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'testing-airflow-dags': 3} | 2.25 | {'ok': 3} |
| testing-custom-operator-conn | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 0% | 0.125 | 0.75 | - | 0.681 | {'task_fail': 1, 'turn_limit': 1} |
| testing-custom-operator-conn | testing | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 1 (1) | 100% | 1 | 1 | {'testing-airflow-dags': 1} | 0.615 | {'ok': 1} |
| testing-custom-operator-conn | testing | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'testing-airflow-dags': 3} | 1.56 | {'ok': 3} |
| testing-dagbag-integrity | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.708 | 0.75 | - | 0.73 | {'turn_limit': 1, 'ok': 2} |
| testing-dagbag-integrity | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | - | 1.31 | {'ok': 3} |
| testing-dagbag-integrity | testing | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.958 | 1 | {'testing-airflow-dags': 2} | 0.597 | {'task_fail': 1, 'ok': 2} |
| testing-dagbag-integrity | testing | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 1 | {'testing-airflow-dags': 3} | 1.45 | {'ok': 3} |

## holdout: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 10 (10) | 0% | 0.489 | 0.733 | 0% | 3.89e+06 | 0.682 | 214 | {'turn_limit': 2, 'task_fail': 8} |
| baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 19 (19) | 37% | 0.804 | 0.649 | 0% | 2.86e+06 | 1.8 | 189 | {'ok': 7, 'task_fail': 11, 'cost_limit': 1} |
| skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 13 (13) | 31% | 0.676 | 0.878 | 77% | 4.44e+06 | 0.873 | 185 | {'ok': 4, 'task_fail': 4, 'turn_limit': 5} |
| skill | google-vertex-anthropic/claude-sonnet-4-6@default | 10 (10) | 90% | 0.99 | 0.933 | 100% | 3.31e+06 | 1.96 | 240 | {'ok': 9, 'task_fail': 1} |

## holdout: paired delta (skill - baseline) over cases

| model | cases | delta pass rate | 95% CI | delta primary score | 95% CI |
|---|---|---|---|---|---|
| google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 | 0.167 | (0.0, 0.5) | 0.0139 | (-0.2917, 0.2778) |
| google-vertex-anthropic/claude-sonnet-4-6@default | 4 | 0.333 | (-0.1666, 0.8334) | 0.0785 | (-0.0167, 0.1736) |
| pooled (7 case x model pairs) | 5 | 0.262 | (-0.037, 0.5556) | 0.0508 | (-0.0492, 0.1519) |

Pooled CI: bootstrap over cases; a resampled case carries the deltas of all its models.

## holdout: per case

| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| authoring-daily-revenue-yesterday | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 33% | 0.778 | 0.778 | - | 2.54 | {'ok': 1, 'task_fail': 1, 'cost_limit': 1} |
| authoring-daily-revenue-yesterday | authoring | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 67% | 0.833 | 0.889 | {'authoring-airflow-dags': 2} | 1 | {'ok': 2, 'task_fail': 1} |
| authoring-daily-revenue-yesterday | authoring | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 100% | 1 | 1 | {'authoring-airflow-dags': 2} | 1.3 | {'ok': 2} |
| authoring-partner-feeds-mapping | authoring | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.444 | 0.889 | - | 0.816 | {'turn_limit': 2, 'task_fail': 1} |
| authoring-partner-feeds-mapping | authoring | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.556 | - | 1.79 | {'ok': 3} |
| authoring-partner-feeds-mapping | authoring | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 0% | 0.722 | 0.833 | {'authoring-airflow-dags': 1} | 1.27 | {'task_fail': 1, 'turn_limit': 1} |
| authoring-partner-feeds-mapping | authoring | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.778 | {'authoring-airflow-dags': 3} | 3.21 | {'ok': 3} |
| debugging-nondeterministic-parse | debugging | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 100% | 1 | 0.667 | - | 0.863 | {'ok': 3} |
| debugging-nondeterministic-parse | debugging | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 50% | 0.95 | 1 | {'authoring-airflow-dags': 1, 'migrating-to-airflow-3': 2} | 0.55 | {'ok': 1, 'task_fail': 1} |
| debugging-nondeterministic-parse | debugging | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 67% | 0.967 | 1 | {'authoring-airflow-dags': 3} | 0.863 | {'ok': 2, 'task_fail': 1} |
| migration-hourly-pageviews-templates | migration | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 0% | 0.357 | 0.167 | - | 0.643 | {'task_fail': 2} |
| migration-hourly-pageviews-templates | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 0% | 0.571 | 0.333 | - | 2.03 | {'task_fail': 2} |
| migration-shipments-assets | migration | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.571 | 0.556 | - | 2.58 | {'task_fail': 3} |
| migration-shipments-assets | migration | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 1 (1) | 0% | 0.857 | 0.333 | {'migrating-to-airflow-3': 1} | 0.75 | {'turn_limit': 1} |
| scheduling-backfill-pageviews | scheduling | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 0% | 0.611 | 0.667 | - | 0.395 | {'task_fail': 2} |
| scheduling-backfill-pageviews | scheduling | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 3 (3) | 0% | 0.778 | 0.667 | - | 1.12 | {'task_fail': 3} |
| scheduling-backfill-pageviews | scheduling | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 2 (2) | 50% | 0.667 | 1 | {'authoring-airflow-dags': 2} | 0.585 | {'task_fail': 1, 'ok': 1} |
| testing-taskflow-transforms | testing | baseline | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.542 | 1 | - | 0.767 | {'task_fail': 3} |
| testing-taskflow-transforms | testing | baseline | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 0% | 0.875 | 1 | - | 1.7 | {'task_fail': 2} |
| testing-taskflow-transforms | testing | skill | google-vertex-anthropic/claude-haiku-4-5@20251001 | 3 (3) | 0% | 0.25 | 0.917 | {'testing-airflow-dags': 2} | 0.931 | {'turn_limit': 3} |
| testing-taskflow-transforms | testing | skill | google-vertex-anthropic/claude-sonnet-4-6@default | 2 (2) | 100% | 1 | 1 | {'testing-airflow-dags': 2} | 2.39 | {'ok': 2} |

## Failure classes (all runs)

{'ok': 76, 'task_fail': 48, 'turn_limit': 18, 'cost_limit': 1}

Total spend (all attempts, all dirs): $169.60

## Isolation

Contamination suspects: 0 run(s). None.
Broad kill commands (pkill/killall/kill by pattern): 0 run(s). None.
Agent env restored after: 0 run(s); restore failed: 0.

## Sources

- `evals/airflow/results/baseline-2026-09-30`: arm=None models=None altimate-code=None started=None budget=None
- `evals/airflow/results/baseline-run3-2026-09-30`: arm=None models=None altimate-code=None started=None budget=None
- `evals/airflow/results/skill-2026-09-30`: arm=None models=None altimate-code=None started=None budget=None
