# altimate-code campaigns 2026-09-30: retroactive contamination rescore

Detector: `isolation.scan_contamination` with today's forbidden roots, rebuilt per campaign (see `evals/harness/rescore_contamination.py`). Inputs: `evals/airflow/results/baseline-2026-09-30`, `evals/airflow/results/baseline-run3-2026-09-30`, `evals/airflow/results/skill-2026-09-30`.
A run is dropped from the excluding tables when its scored attempt is flagged. Evidence strength is a heuristic: `strong` = the attempt used a shared-temp path another attempt had used earlier without overwriting it first, used a non-temp forbidden root, or overwrote a shared-temp path that another attempt also wrote before this attempt's last use of it (a race); `weak` = no sign of another attempt's state: paths this attempt overwrote first with no concurrent writer (e.g. `> <tmp>/summary.md`), per-process names (`<tmp>/x_$$`, `mktemp`), a mistyped path to its own scratch dir, or shared-temp paths no earlier attempt used. Manual review of the strong hits: `REVIEW.md`.

## Flagged scored attempts

| split | arm | model | attempts | flagged | strong | flagged & passed | flagged & failed | no events |
|---|---|---|---|---|---|---|---|---|
| dev | baseline | Haiku 4.5 | 39 | 19 | 1 | 6 | 13 | 0 |
| dev | baseline | Sonnet 4.6 | 39 | 9 | 2 | 8 | 1 | 0 |
| dev | skill | Haiku 4.5 | 39 | 15 | 3 | 13 | 2 | 0 |
| dev | skill | Sonnet 4.6 | 39 | 22 | 6 | 21 | 1 | 0 |
| holdout | baseline | Haiku 4.5 | 21 | 11 | 1 | 4 | 7 | 0 |
| holdout | baseline | Sonnet 4.6 | 21 | 2 | 1 | 1 | 1 | 0 |
| holdout | skill | Haiku 4.5 | 21 | 8 | 2 | 1 | 7 | 0 |
| holdout | skill | Sonnet 4.6 | 21 | 11 | 3 | 8 | 3 | 0 |

Hit roots (scored attempts with at least one hit): {'work-root': 9, 'shared-temp': 92}.

## Strong-evidence attempts

- dev baseline Sonnet 4.6 `authoring-vendor-shipments-etl` run 3 [ok]: bash `<tmp>/landing` (shared-temp, first use, 1 earlier user(s), 0 concurrent writer(s))
- dev baseline Haiku 4.5 `debugging-variable-at-parse` run 3 [ok]: bash `<work>/baseline-run3-2026-09-30-baseline-20260930-082417` (work-root, first use, 0 earlier user(s), 0 concurrent writer(s))
- holdout baseline Haiku 4.5 `scheduling-backfill-pageviews` run 3 [task_fail]: bash `<tmp>/airflow_test` (shared-temp, first use, 1 earlier user(s), 0 concurrent writer(s))
- dev baseline Sonnet 4.6 `testing-custom-operator-conn` run 3 [ok]: bash `<tmp>/test.duckdb` (shared-temp, first use, 1 earlier user(s), 0 concurrent writer(s))
- holdout baseline Sonnet 4.6 `testing-taskflow-transforms` run 3 [ok]: bash `<tmp>/airflow_test` (shared-temp, first use, 2 earlier user(s), 0 concurrent writer(s))
- dev skill Sonnet 4.6 `debugging-variable-at-parse` run 1 [ok]: bash `<tmp>/before.json` (shared-temp, first overwrite, 3 earlier user(s), 2 concurrent writer(s))
- holdout skill Sonnet 4.6 `migration-hourly-pageviews-templates` run 1 [ok]: bash `<tmp>/before.json` (shared-temp, first overwrite, 3 earlier user(s), 1 concurrent writer(s))
- dev skill Sonnet 4.6 `migration-inventory-context` run 1 [ok]: bash `<tmp>/before.json` (shared-temp, first overwrite, 6 earlier user(s), 2 concurrent writer(s))
- dev skill Sonnet 4.6 `migration-revenue-previous-day` run 1 [ok]: bash `<tmp>/before.json` (shared-temp, first overwrite, 6 earlier user(s), 1 concurrent writer(s))
- holdout skill Sonnet 4.6 `migration-hourly-pageviews-templates` run 2 [ok]: bash `<tmp>/before.json` (shared-temp, first overwrite, 13 earlier user(s), 2 concurrent writer(s))
- holdout skill Haiku 4.5 `migration-hourly-pageviews-templates` run 2 [task_fail]: bash `<tmp>/before.json` (shared-temp, first overwrite, 13 earlier user(s), 1 concurrent writer(s))
- dev skill Sonnet 4.6 `migration-revenue-previous-day` run 2 [ok]: bash `<tmp>/before.json` (shared-temp, first overwrite, 17 earlier user(s), 1 concurrent writer(s))
- dev skill Haiku 4.5 `scheduling-idempotent-orders-load` run 2 [ok]: bash `<tmp>/airflow_test` (shared-temp, first use, 3 earlier user(s), 0 concurrent writer(s))
- dev skill Haiku 4.5 `debugging-variable-at-parse` run 3 [ok]: bash `<tmp>/test_warehouse` (shared-temp, first use, 1 earlier user(s), 0 concurrent writer(s))
- holdout skill Haiku 4.5 `migration-hourly-pageviews-templates` run 3 [task_fail]: bash `<tmp>/after.json` (shared-temp, first use, 18 earlier user(s), 0 concurrent writer(s))
- holdout skill Sonnet 4.6 `migration-hourly-pageviews-templates` run 3 [ok]: bash `<tmp>/before.json` (shared-temp, first overwrite, 22 earlier user(s), 1 concurrent writer(s))
- dev skill Sonnet 4.6 `migration-revenue-previous-day` run 3 [ok]: bash `<tmp>/before.json` (shared-temp, first overwrite, 25 earlier user(s), 1 concurrent writer(s)); bash `<tmp>/after.json` (shared-temp, first overwrite, 21 earlier user(s), 1 concurrent writer(s))
- dev skill Sonnet 4.6 `migration-weekly-catchup` run 3 [ok]: bash `<tmp>/before.json` (shared-temp, first overwrite, 27 earlier user(s), 1 concurrent writer(s)); bash `<tmp>/after.json` (shared-temp, first overwrite, 23 earlier user(s), 1 concurrent writer(s))
- dev skill Haiku 4.5 `testing-custom-operator-conn` run 3 [turn_limit]: bash `<tmp>/test.duckdb` (shared-temp, first use, 2 earlier user(s), 0 concurrent writer(s))

Flagged non-scored (retried infra_error) attempts: 0.

## Pass rate: All runs

| split | model | baseline pass (n) | skill pass (n) | paired delta [95% CI] | cases |
|---|---|---|---|---|---|
| dev | Haiku 4.5 | 14/39 (36%) | 31/39 (79%) | +0.44 [+0.18, +0.67] | 13 |
| holdout | Haiku 4.5 | 4/21 (19%) | 5/21 (24%) | +0.05 [+0.00, +0.14] | 7 |
| dev | Sonnet 4.6 | 22/39 (56%) | 37/39 (95%) | +0.38 [+0.15, +0.62] | 13 |
| holdout | Sonnet 4.6 | 8/21 (38%) | 17/21 (81%) | +0.43 [+0.05, +0.76] | 7 |
| dev | pooled (26 pairs, CI clustered by case) | | | +0.41 [+0.21, +0.62] | 13 |
| holdout | pooled (14 pairs, CI clustered by case) | | | +0.24 [+0.02, +0.43] | 7 |

## Pass rate: Excluding flagged runs

| split | model | baseline pass (n) | skill pass (n) | paired delta [95% CI] | cases |
|---|---|---|---|---|---|
| dev | Haiku 4.5 | 8/20 (40%) | 18/24 (75%) | +0.43 [+0.09, +0.78] | 9 |
| holdout | Haiku 4.5 | 0/10 (0%) | 4/13 (31%) | +0.17 [+0.00, +0.50] | 3 |
| dev | Sonnet 4.6 | 14/30 (47%) | 16/17 (94%) | +0.22 [+0.06, +0.39] | 6 |
| holdout | Sonnet 4.6 | 7/19 (37%) | 9/10 (90%) | +0.33 [-0.17, +0.83] | 4 |
| dev | pooled (15 pairs, CI clustered by case) | | | +0.34 [+0.11, +0.63] | 10 |
| holdout | pooled (7 pairs, CI clustered by case) | | | +0.26 [-0.04, +0.56] | 5 |

## Pass rate: Excluding strong-evidence runs only (sensitivity)

| split | model | baseline pass (n) | skill pass (n) | paired delta [95% CI] | cases |
|---|---|---|---|---|---|
| dev | Haiku 4.5 | 13/38 (34%) | 29/36 (81%) | +0.46 [+0.21, +0.69] | 13 |
| holdout | Haiku 4.5 | 4/20 (20%) | 5/19 (26%) | +0.05 [+0.00, +0.14] | 7 |
| dev | Sonnet 4.6 | 20/37 (54%) | 31/33 (94%) | +0.33 [+0.11, +0.58] | 12 |
| holdout | Sonnet 4.6 | 7/20 (35%) | 14/18 (78%) | +0.39 [+0.00, +0.78] | 6 |
| dev | pooled (25 pairs, CI clustered by case) | | | +0.40 [+0.20, +0.61] | 13 |
| holdout | pooled (13 pairs, CI clustered by case) | | | +0.21 [+0.00, +0.43] | 7 |

Paired delta = mean over cases of (skill - baseline) pass rate, same case and model; 95% CI is a percentile bootstrap over cases (10,000 resamples, seed 0). Pooled rows average every (case, model) pair and resample cases with all their models.

## Per-case paired deltas (skill - baseline pass rate)

`-` = no valid pair left after exclusion.

| split | model | case | baseline (all) | skill (all) | delta (all) | delta (excl. flagged) | delta (excl. strong) |
|---|---|---|---|---|---|---|---|
| dev | Haiku 4.5 | `authoring-airflow2-inventory-snapshot` | 67% | 67% | +0.00 | +0.00 | +0.00 |
| dev | Haiku 4.5 | `authoring-clickstream-claim-check` | 33% | 67% | +0.33 | +0.17 | +0.33 |
| dev | Haiku 4.5 | `authoring-vendor-shipments-etl` | 33% | 33% | +0.00 | - | +0.00 |
| dev | Haiku 4.5 | `debugging-manual-trigger-context` | 0% | 67% | +0.67 | - | +0.67 |
| dev | Haiku 4.5 | `debugging-variable-at-parse` | 100% | 100% | +0.00 | - | +0.00 |
| dev | Haiku 4.5 | `migration-inventory-context` | 0% | 100% | +1.00 | +1.00 | +1.00 |
| dev | Haiku 4.5 | `migration-revenue-previous-day` | 0% | 100% | +1.00 | +1.00 | +1.00 |
| dev | Haiku 4.5 | `migration-weekly-catchup` | 0% | 100% | +1.00 | - | +1.00 |
| dev | Haiku 4.5 | `scheduling-idempotent-orders-load` | 33% | 100% | +0.67 | +0.00 | +0.67 |
| dev | Haiku 4.5 | `scheduling-weekday-ny-business-day` | 33% | 100% | +0.67 | +1.00 | +0.67 |
| dev | Haiku 4.5 | `testing-airflow2-ci-suite` | 100% | 67% | -0.33 | -0.33 | -0.33 |
| dev | Haiku 4.5 | `testing-custom-operator-conn` | 0% | 67% | +0.67 | +1.00 | +1.00 |
| dev | Haiku 4.5 | `testing-dagbag-integrity` | 67% | 67% | +0.00 | +0.00 | +0.00 |
| dev | Sonnet 4.6 | `authoring-airflow2-inventory-snapshot` | 100% | 100% | +0.00 | +0.00 | +0.00 |
| dev | Sonnet 4.6 | `authoring-clickstream-claim-check` | 100% | 100% | +0.00 | - | +0.00 |
| dev | Sonnet 4.6 | `authoring-vendor-shipments-etl` | 100% | 100% | +0.00 | - | +0.00 |
| dev | Sonnet 4.6 | `debugging-manual-trigger-context` | 0% | 33% | +0.33 | +0.50 | +0.33 |
| dev | Sonnet 4.6 | `debugging-variable-at-parse` | 0% | 100% | +1.00 | - | +1.00 |
| dev | Sonnet 4.6 | `migration-inventory-context` | 0% | 100% | +1.00 | - | +1.00 |
| dev | Sonnet 4.6 | `migration-revenue-previous-day` | 0% | 100% | +1.00 | - | - |
| dev | Sonnet 4.6 | `migration-weekly-catchup` | 0% | 100% | +1.00 | - | +1.00 |
| dev | Sonnet 4.6 | `scheduling-idempotent-orders-load` | 67% | 100% | +0.33 | +0.50 | +0.33 |
| dev | Sonnet 4.6 | `scheduling-weekday-ny-business-day` | 67% | 100% | +0.33 | +0.33 | +0.33 |
| dev | Sonnet 4.6 | `testing-airflow2-ci-suite` | 100% | 100% | +0.00 | +0.00 | +0.00 |
| dev | Sonnet 4.6 | `testing-custom-operator-conn` | 100% | 100% | +0.00 | - | +0.00 |
| dev | Sonnet 4.6 | `testing-dagbag-integrity` | 100% | 100% | +0.00 | +0.00 | +0.00 |
| holdout | Haiku 4.5 | `authoring-daily-revenue-yesterday` | 67% | 67% | +0.00 | - | +0.00 |
| holdout | Haiku 4.5 | `authoring-partner-feeds-mapping` | 0% | 0% | +0.00 | +0.00 | +0.00 |
| holdout | Haiku 4.5 | `debugging-nondeterministic-parse` | 67% | 67% | +0.00 | - | +0.00 |
| holdout | Haiku 4.5 | `migration-hourly-pageviews-templates` | 0% | 0% | +0.00 | - | +0.00 |
| holdout | Haiku 4.5 | `migration-shipments-assets` | 0% | 0% | +0.00 | - | +0.00 |
| holdout | Haiku 4.5 | `scheduling-backfill-pageviews` | 0% | 33% | +0.33 | +0.50 | +0.33 |
| holdout | Haiku 4.5 | `testing-taskflow-transforms` | 0% | 0% | +0.00 | +0.00 | +0.00 |
| holdout | Sonnet 4.6 | `authoring-daily-revenue-yesterday` | 33% | 100% | +0.67 | +0.67 | +0.67 |
| holdout | Sonnet 4.6 | `authoring-partner-feeds-mapping` | 100% | 100% | +0.00 | +0.00 | +0.00 |
| holdout | Sonnet 4.6 | `debugging-nondeterministic-parse` | 100% | 67% | -0.33 | -0.33 | -0.33 |
| holdout | Sonnet 4.6 | `migration-hourly-pageviews-templates` | 0% | 100% | +1.00 | - | - |
| holdout | Sonnet 4.6 | `migration-shipments-assets` | 0% | 0% | +0.00 | - | +0.00 |
| holdout | Sonnet 4.6 | `scheduling-backfill-pageviews` | 0% | 100% | +1.00 | - | +1.00 |
| holdout | Sonnet 4.6 | `testing-taskflow-transforms` | 33% | 100% | +0.67 | +1.00 | +1.00 |

## Do conclusions change when flagged runs are dropped?

Significant = 95% CI excludes 0.

| split | model | delta all [CI] | delta excl. flagged [CI] | same sign | same significance |
|---|---|---|---|---|---|
| dev | Haiku 4.5 | +0.44 [+0.18, +0.67] (13 cases) | +0.43 [+0.09, +0.78] (9 cases) | yes | yes |
| dev | Sonnet 4.6 | +0.38 [+0.15, +0.62] (13 cases) | +0.22 [+0.06, +0.39] (6 cases) | yes | yes |
| dev | pooled (clustered by case) | +0.41 [+0.21, +0.62] (13 cases) | +0.34 [+0.11, +0.63] (10 cases) | yes | yes |
| holdout | Haiku 4.5 | +0.05 [+0.00, +0.14] (7 cases) | +0.17 [+0.00, +0.50] (3 cases) | yes | yes |
| holdout | Sonnet 4.6 | +0.43 [+0.05, +0.76] (7 cases) | +0.33 [-0.17, +0.83] (4 cases) | yes | **no** |
| holdout | pooled (clustered by case) | +0.24 [+0.02, +0.43] (7 cases) | +0.26 [-0.04, +0.56] (5 cases) | yes | **no** |
