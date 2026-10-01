# Airflow skill eval report

Pass rate = fraction of valid runs whose primary checks all passed. Excluded runs (infra_error, grader_error, skipped_budget) are listed but not counted.

## dev: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | claude-opus-5-5 | 13 (13) | 92% | 0.987 | 0.923 | 0% | 3.66e+05 | 0.437 | 231 | {'ok': 12, 'task_fail': 1} |
| baseline | claude-sonnet-5-5 | 13 (13) | 92% | 0.985 | 0.846 | 0% | 1.79e+05 | 0.133 | 45.4 | {'ok': 12, 'task_fail': 1} |
| skill | claude-opus-5-5 | 13 (13) | 92% | 0.985 | 1 | 100% | 5.7e+05 | 0.579 | 272 | {'ok': 12, 'task_fail': 1} |
| skill | claude-sonnet-5-5 | 13 (13) | 92% | 0.985 | 0.923 | 100% | 2.73e+05 | 0.206 | 144 | {'ok': 12, 'task_fail': 1} |

## dev: paired delta (skill - baseline) over cases

| model | cases | delta pass rate | 95% CI | delta primary score | 95% CI |
|---|---|---|---|---|---|
| claude-opus-5-5 | 13 | 0 | (-0.2308, 0.2308) | -0.0026 | (-0.0462, 0.0385) |
| claude-sonnet-5-5 | 13 | 0 | (0.0, 0.0) | 0 | (0.0, 0.0) |
| pooled (26 case x model pairs) | 13 | 0 | (-0.1154, 0.1154) | -0.0013 | (-0.0231, 0.0192) |

Pooled CI: bootstrap over cases; a resampled case carries the deltas of all its models.

## dev: per case

| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| authoring-airflow2-inventory-snapshot | authoring | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.251 | {'ok': 1} |
| authoring-airflow2-inventory-snapshot | authoring | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.123 | {'ok': 1} |
| authoring-airflow2-inventory-snapshot | authoring | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.454 | {'ok': 1} |
| authoring-airflow2-inventory-snapshot | authoring | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.186 | {'ok': 1} |
| authoring-clickstream-claim-check | authoring | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.438 | {'ok': 1} |
| authoring-clickstream-claim-check | authoring | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.147 | {'ok': 1} |
| authoring-clickstream-claim-check | authoring | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 1.23 | {'ok': 1} |
| authoring-clickstream-claim-check | authoring | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.178 | {'ok': 1} |
| authoring-vendor-shipments-etl | authoring | baseline | claude-opus-5-5 | 1 (1) | 0% | 0.833 | 1 | - | 0.401 | {'task_fail': 1} |
| authoring-vendor-shipments-etl | authoring | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 0.667 | - | 0.089 | {'ok': 1} |
| authoring-vendor-shipments-etl | authoring | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.696 | {'ok': 1} |
| authoring-vendor-shipments-etl | authoring | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 0.333 | {'authoring-airflow-dags': 1} | 0.209 | {'ok': 1} |
| debugging-manual-trigger-context | debugging | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 0.667 | - | 0.392 | {'ok': 1} |
| debugging-manual-trigger-context | debugging | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 0.667 | - | 0.119 | {'ok': 1} |
| debugging-manual-trigger-context | debugging | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'migrating-to-airflow-3': 1} | 0.501 | {'ok': 1} |
| debugging-manual-trigger-context | debugging | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 0.667 | {'migrating-to-airflow-3': 1} | 0.156 | {'ok': 1} |
| debugging-variable-at-parse | debugging | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.269 | {'ok': 1} |
| debugging-variable-at-parse | debugging | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 0.667 | - | 0.0727 | {'ok': 1} |
| debugging-variable-at-parse | debugging | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'migrating-to-airflow-3': 1} | 0.465 | {'ok': 1} |
| debugging-variable-at-parse | debugging | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'migrating-to-airflow-3': 1} | 0.152 | {'ok': 1} |
| migration-inventory-context | migration | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 0.667 | - | 0.493 | {'ok': 1} |
| migration-inventory-context | migration | baseline | claude-sonnet-5-5 | 1 (1) | 0% | 0.8 | 0.667 | - | 0.152 | {'task_fail': 1} |
| migration-inventory-context | migration | skill | claude-opus-5-5 | 1 (1) | 0% | 0.8 | 1 | {'migrating-to-airflow-3': 1} | 0.609 | {'task_fail': 1} |
| migration-inventory-context | migration | skill | claude-sonnet-5-5 | 1 (1) | 0% | 0.8 | 1 | {'migrating-to-airflow-3': 1} | 0.377 | {'task_fail': 1} |
| migration-revenue-previous-day | migration | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 0.667 | - | 0.498 | {'ok': 1} |
| migration-revenue-previous-day | migration | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 0.667 | - | 0.199 | {'ok': 1} |
| migration-revenue-previous-day | migration | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'migrating-to-airflow-3': 1} | 0.757 | {'ok': 1} |
| migration-revenue-previous-day | migration | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'migrating-to-airflow-3': 1} | 0.28 | {'ok': 1} |
| migration-weekly-catchup | migration | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.877 | {'ok': 1} |
| migration-weekly-catchup | migration | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.181 | {'ok': 1} |
| migration-weekly-catchup | migration | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'migrating-to-airflow-3': 1} | 0.478 | {'ok': 1} |
| migration-weekly-catchup | migration | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'migrating-to-airflow-3': 1} | 0.226 | {'ok': 1} |
| scheduling-idempotent-orders-load | scheduling | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.461 | {'ok': 1} |
| scheduling-idempotent-orders-load | scheduling | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 0.667 | - | 0.132 | {'ok': 1} |
| scheduling-idempotent-orders-load | scheduling | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.393 | {'ok': 1} |
| scheduling-idempotent-orders-load | scheduling | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.159 | {'ok': 1} |
| scheduling-weekday-ny-business-day | scheduling | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.221 | {'ok': 1} |
| scheduling-weekday-ny-business-day | scheduling | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.0882 | {'ok': 1} |
| scheduling-weekday-ny-business-day | scheduling | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.456 | {'ok': 1} |
| scheduling-weekday-ny-business-day | scheduling | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.164 | {'ok': 1} |
| testing-airflow2-ci-suite | testing | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.714 | {'ok': 1} |
| testing-airflow2-ci-suite | testing | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.179 | {'ok': 1} |
| testing-airflow2-ci-suite | testing | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'testing-airflow-dags': 1} | 0.645 | {'ok': 1} |
| testing-airflow2-ci-suite | testing | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'testing-airflow-dags': 1} | 0.244 | {'ok': 1} |
| testing-custom-operator-conn | testing | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.312 | {'ok': 1} |
| testing-custom-operator-conn | testing | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.107 | {'ok': 1} |
| testing-custom-operator-conn | testing | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'testing-airflow-dags': 1} | 0.458 | {'ok': 1} |
| testing-custom-operator-conn | testing | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'testing-airflow-dags': 1} | 0.21 | {'ok': 1} |
| testing-dagbag-integrity | testing | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.35 | {'ok': 1} |
| testing-dagbag-integrity | testing | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.139 | {'ok': 1} |
| testing-dagbag-integrity | testing | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'testing-airflow-dags': 1} | 0.377 | {'ok': 1} |
| testing-dagbag-integrity | testing | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'testing-airflow-dags': 1} | 0.144 | {'ok': 1} |

## holdout: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | claude-opus-5-5 | 7 (7) | 100% | 1 | 0.905 | 0% | 5.27e+05 | 0.54 | 334 | {'ok': 7} |
| baseline | claude-sonnet-5-5 | 7 (7) | 86% | 0.939 | 0.857 | 0% | 1.93e+05 | 0.139 | 83.2 | {'ok': 6, 'task_fail': 1} |
| skill | claude-opus-5-5 | 7 (7) | 100% | 1 | 0.952 | 100% | 5.41e+05 | 0.591 | 377 | {'ok': 7} |
| skill | claude-sonnet-5-5 | 7 (7) | 100% | 1 | 0.952 | 100% | 2.94e+05 | 0.228 | 196 | {'ok': 7} |

## holdout: paired delta (skill - baseline) over cases

| model | cases | delta pass rate | 95% CI | delta primary score | 95% CI |
|---|---|---|---|---|---|
| claude-opus-5-5 | 7 | 0 | (0.0, 0.0) | 0 | (0.0, 0.0) |
| claude-sonnet-5-5 | 7 | 0.143 | (0.0, 0.4286) | 0.0612 | (0.0, 0.1837) |
| pooled (14 case x model pairs) | 7 | 0.0714 | (0.0, 0.2143) | 0.0306 | (0.0, 0.0918) |

Pooled CI: bootstrap over cases; a resampled case carries the deltas of all its models.

## holdout: per case

| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| authoring-daily-revenue-yesterday | authoring | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.233 | {'ok': 1} |
| authoring-daily-revenue-yesterday | authoring | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.118 | {'ok': 1} |
| authoring-daily-revenue-yesterday | authoring | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.469 | {'ok': 1} |
| authoring-daily-revenue-yesterday | authoring | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.132 | {'ok': 1} |
| authoring-partner-feeds-mapping | authoring | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.415 | {'ok': 1} |
| authoring-partner-feeds-mapping | authoring | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.108 | {'ok': 1} |
| authoring-partner-feeds-mapping | authoring | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.524 | {'ok': 1} |
| authoring-partner-feeds-mapping | authoring | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.206 | {'ok': 1} |
| debugging-nondeterministic-parse | debugging | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.472 | {'ok': 1} |
| debugging-nondeterministic-parse | debugging | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.0999 | {'ok': 1} |
| debugging-nondeterministic-parse | debugging | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.514 | {'ok': 1} |
| debugging-nondeterministic-parse | debugging | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'authoring-airflow-dags': 1} | 0.197 | {'ok': 1} |
| migration-hourly-pageviews-templates | migration | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 0.667 | - | 0.336 | {'ok': 1} |
| migration-hourly-pageviews-templates | migration | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 0.667 | - | 0.213 | {'ok': 1} |
| migration-hourly-pageviews-templates | migration | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'migrating-to-airflow-3': 1} | 0.728 | {'ok': 1} |
| migration-hourly-pageviews-templates | migration | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'migrating-to-airflow-3': 1} | 0.196 | {'ok': 1} |
| migration-shipments-assets | migration | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 0.667 | - | 0.77 | {'ok': 1} |
| migration-shipments-assets | migration | baseline | claude-sonnet-5-5 | 1 (1) | 0% | 0.571 | 0.667 | - | 0.172 | {'task_fail': 1} |
| migration-shipments-assets | migration | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'migrating-to-airflow-3': 1} | 0.595 | {'ok': 1} |
| migration-shipments-assets | migration | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'migrating-to-airflow-3': 1} | 0.255 | {'ok': 1} |
| scheduling-backfill-pageviews | scheduling | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.417 | {'ok': 1} |
| scheduling-backfill-pageviews | scheduling | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 0.667 | - | 0.0835 | {'ok': 1} |
| scheduling-backfill-pageviews | scheduling | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 0.667 | {'authoring-airflow-dags': 1} | 0.514 | {'ok': 1} |
| scheduling-backfill-pageviews | scheduling | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 0.667 | {'authoring-airflow-dags': 1} | 0.241 | {'ok': 1} |
| testing-taskflow-transforms | testing | baseline | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | - | 1.13 | {'ok': 1} |
| testing-taskflow-transforms | testing | baseline | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | - | 0.176 | {'ok': 1} |
| testing-taskflow-transforms | testing | skill | claude-opus-5-5 | 1 (1) | 100% | 1 | 1 | {'testing-airflow-dags': 1} | 0.793 | {'ok': 1} |
| testing-taskflow-transforms | testing | skill | claude-sonnet-5-5 | 1 (1) | 100% | 1 | 1 | {'testing-airflow-dags': 1} | 0.366 | {'ok': 1} |

## Failure classes (all runs)

{'ok': 75, 'task_fail': 5}

Total spend (all attempts, all dirs): $28.09

## Isolation

Contamination suspects: 14 run(s).
- authoring-airflow2-inventory-snapshot baseline claude-sonnet-5-5 run 1: bash:<tmp>/af_home (shared-temp)
- migration-inventory-context baseline claude-sonnet-5-5 run 1: bash:<tmp>/af3 (shared-temp)
- migration-hourly-pageviews-templates baseline claude-sonnet-5-5 run 1: bash:<work>/ (work-root)
- authoring-clickstream-claim-check skill claude-sonnet-5-5 run 1: bash:~/.cache/des-evals/work/ (work-root)
- migration-hourly-pageviews-templates skill claude-sonnet-5-5 run 1: bash:~/.claude/skills/migrating-to-airflow-3 (user-skills)
- debugging-nondeterministic-parse skill claude-sonnet-5-5 run 1: bash:~/.cache/des-evals/work/ (work-root), bash:~/.cache/des-evals/work/ (work-root)
- migration-revenue-previous-day skill claude-sonnet-5-5 run 1: bash:~/.cache/des-evals/work/ (work-root)
- migration-inventory-context skill claude-sonnet-5-5 run 1: bash:<tmp>/edit.py (shared-temp), bash:<tmp>/edit.py (shared-temp)
- scheduling-idempotent-orders-load skill claude-sonnet-5-5 run 1: bash:~/.cache/des-evals/work/ (work-root)
- scheduling-weekday-ny-business-day skill claude-sonnet-5-5 run 1: bash:~/.cache/des-evals/work/ (work-root), bash:~/.cache/des-evals/work/ (work-root)
- testing-custom-operator-conn skill claude-sonnet-5-5 run 1: bash:~/.cache/des-evals/work/ (work-root), bash:<work>/ (work-root)
- authoring-vendor-shipments-etl skill claude-sonnet-5-5 run 1: bash:<tmp>/land (shared-temp), bash:<tmp>/land/ (shared-temp), bash:<tmp>/land (shared-temp)
- testing-taskflow-transforms skill claude-sonnet-5-5 run 1: bash:~/.cache/des-evals/work/ (work-root)
- debugging-variable-at-parse skill claude-opus-5-5 run 1: bash:<tmp>/wh (shared-temp)
Broad kill commands (pkill/killall/kill by pattern): 5 run(s).
- authoring-vendor-shipments-etl skill claude-sonnet-5-5 run 1: pkill -f replay_runs; cat <work>/final-core-skill-claude-sonnet-5-5-2026-10-01-skill-20261001-044302/authoring-vendor-sh
- testing-taskflow-transforms skill claude-sonnet-5-5 run 1: sleep 60; cat "<work>/final-core-skill-claude-sonnet-5-5-2026-10-01-skill-20261001-044302/testing-taskflow-transforms-3b
- authoring-partner-feeds-mapping baseline claude-opus-5-5 run 1: cd <work>/final-core-baseline-claude-opus-5-5-2026-10-01-baseline-20261001-075851/authoring-partner-feeds-mapping-58kori
- scheduling-backfill-pageviews baseline claude-opus-5-5 run 1: cd <work>/final-core-baseline-claude-opus-5-5-2026-10-01-baseline-20261001-075851/scheduling-backfill-pageviews-s0w_1zf8
- scheduling-idempotent-orders-load baseline claude-opus-5-5 run 1: cat "<work>/final-core-baseline-claude-opus-5-5-2026-10-01-baseline-20261001-075851/scheduling-idempotent-orders-load-7k
Agent env restored after: 0 run(s); restore failed: 0.

## Sources

- `evals/airflow/results/final-core-baseline-claude-sonnet-5-5-2026-10-01`: arm=baseline models=['claude-sonnet-5-5'] claude-code=2.1.286 started=2026-10-01T11:35:37+00:00 budget={'cap_usd': 2000.0, 'per_run_cap_usd': {'claude-sonnet-5-5': 6.0}, 'spent_usd': 2.6999, 'stopped_early': False}
- `evals/airflow/results/final-core-skill-claude-sonnet-5-5-2026-10-01`: arm=skill models=['claude-sonnet-5-5'] claude-code=2.1.286 started=2026-10-01T11:43:04+00:00 budget={'cap_usd': 2000.0, 'per_run_cap_usd': {'claude-sonnet-5-5': 6.0}, 'spent_usd': 4.2775, 'stopped_early': False}
- `evals/airflow/results/final-core-baseline-claude-opus-5-5-2026-10-01`: arm=baseline models=['claude-opus-5-5'] claude-code=2.1.286 started=2026-10-01T14:58:56+00:00 budget={'cap_usd': 2000.0, 'per_run_cap_usd': {'claude-opus-5-5': 12.0}, 'spent_usd': 9.4559, 'stopped_early': False}
- `evals/airflow/results/final-core-skill-claude-opus-5-5-2026-10-01`: arm=skill models=['claude-opus-5-5'] claude-code=2.1.286 started=2026-10-01T15:29:07+00:00 budget={'cap_usd': 2000.0, 'per_run_cap_usd': {'claude-opus-5-5': 12.0}, 'spent_usd': 11.6585, 'stopped_early': False}
