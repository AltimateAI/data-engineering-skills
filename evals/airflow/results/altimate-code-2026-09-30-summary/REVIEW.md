# Manual review of strong-evidence hits

Each strong hit was checked by hand against the attempt's stored `events.jsonl` (tool input and
output). The other flagged scored attempts are `weak`. Their hits are one of:

- a shared-temp file the attempt wrote first, with no other attempt writing it in between (mostly
  `<tmp>/before.json`, `<tmp>/after.json` and `<tmp>/*summary*.md`);
- a per-process temp name (`$$`, `mktemp`);
- a mistyped path to the attempt's own scratch dir, which failed or created a stray dir.

## 1. `<tmp>/before.json` / `<tmp>/after.json` races (skill arm only)

`skills/airflow/migrating-to-airflow-3/SKILL.md` (frozen, lines 56, 90 and 223-224) tells the agent
to write its BEFORE/AFTER schedule previews to the fixed paths `<tmp>/before.json` and `<tmp>/after.json`.
In these campaigns `<tmp>` was shared and runs went in parallel, so concurrent skill-arm runs overwrote
each other's previews. The stored tool outputs show that the race happened:

| Model | Case, run | Status | What the agent saw |
|---|---|---|---|
| Sonnet 4.6 | `debugging-variable-at-parse` 1 | ok | compare listed `hourly_pageviews`, `order_status_report` (other cases) as missing_before/after |
| Sonnet 4.6 | `migration-revenue-previous-day` 1 | ok | BEFORE preview held `inventory_snapshot` (other case) |
| Sonnet 4.6 | `migration-revenue-previous-day` 3 | ok | read a preview holding `carrier_scorecard`, `ingest_shipments` (other case) |
| Sonnet 4.6 | `migration-hourly-pageviews-templates` 2 | ok | "BEFORE dags: ['inventory_snapshot']" (other case) |
| Haiku 4.5 | `migration-hourly-pageviews-templates` 2 | task_fail | a later read showed `inventory_snapshot` (other case) |
| Haiku 4.5 | `migration-hourly-pageviews-templates` 3 | task_fail | compared `before.json`/`after.json` written by earlier attempts before writing its own |
| Sonnet 4.6 | `migration-hourly-pageviews-templates` 1 and 3, `migration-inventory-context` 1, `migration-weekly-catchup` 3 | ok | a concurrent writer existed. The compare showed own DAGs only (`match` or `missing_before`), so it may have been clobbered or emptied |

These files hold schedule previews (DAG ids, timetables, next run dates), not code, and graders never
read them. A clobbered file corrupts the agent's self-check. It cannot hand the agent another case's
solution. The likely effect is noise or a wasted turn, not an inflated pass. This is still a defect in
the frozen skill: fixed `<tmp>` paths are unsafe whenever two migrations share a machine. They should
use `$TMPDIR` or a path in the project.

## 2. Other strong hits

| Arm / model | Case, run | Status | Hit | Verdict |
|---|---|---|---|---|
| baseline Sonnet 4.6 | `authoring-vendor-shipments-etl` 3 | ok | `<tmp>/landing` | String that a mocked `Variable.get` returns in an import probe. Nothing read. Benign. |
| baseline Haiku 4.5 | `debugging-variable-at-parse` 3 | ok | `find <work>/<campaign> -name warehouse_load.py` | Searched the whole campaign dir, which holds other attempts. Found only its own file. No other attempt's content was read. Low risk. |
| baseline Haiku 4.5 | `scheduling-backfill-pageviews` 3 | task_fail | `os.environ['AIRFLOW_HOME'] = '<tmp>/airflow_test'` | Import probe pointed at a shared `AIRFLOW_HOME` that another attempt had used. Shared Airflow state is possible. The run failed. |
| baseline Sonnet 4.6 | `testing-custom-operator-conn` 3 | ok | `host='<tmp>/test.duckdb'` | Connection host string in an in-memory probe. Benign. |
| baseline Sonnet 4.6 | `testing-taskflow-transforms` 3 | ok | `os.environ.setdefault('AIRFLOW_HOME', '<tmp>/airflow_test')` | `setdefault` does not override the `AIRFLOW_HOME` the harness set. Benign. |
| skill Haiku 4.5 | `scheduling-idempotent-orders-load` 2 | ok | `AIRFLOW_HOME=<tmp>/airflow_test mkdir -p ... && airflow db migrate` | The prefix applied only to `mkdir`; `airflow db migrate` used the attempt's own `AIRFLOW_HOME`. Benign. |
| skill Haiku 4.5 | `debugging-variable-at-parse` 3 | ok | `AIRFLOW_VAR_WAREHOUSE_PATH='<tmp>/test_warehouse'` | Variable value in a parse probe. Benign. |
| skill Haiku 4.5 | `testing-custom-operator-conn` 3 | turn_limit | `host='<tmp>/test.duckdb'` | Connection host string. Benign. |

## Conclusion

No passing run used another attempt's code or outputs to pass a grader. The confirmed
cross-run contamination is the skill-induced preview race in section 1. It corrupted the agent's
own verification signal in the skill arm. If it had any effect on pass rates, it pushed the skill
arm down, not up.

## Effect on the pass-rate conclusions

Tables and the mechanical check are in `REPORT.md` (`results.json` holds the same data).
97 of 240 scored attempts are flagged (41 baseline, 56 skill); 19 are strong. The weak flags
are mostly `<tmp>/before.json` and `<tmp>/after.json` writes that the frozen migration skill
tells the agent to make, so the excluding-flagged table drops skill-arm passes much more often
than baseline runs (dev Sonnet 4.6 skill: 39 to 17 runs). That table is a stress test with a
known bias, not a cleaner estimate.

- Dev: the skill gain holds in every variant. Haiku 4.5 +0.44 to +0.43, Sonnet 4.6 +0.38 to
  +0.22, pooled +0.41 [+0.21, +0.62] to +0.34 [+0.11, +0.63]. All CIs stay above 0.
- Holdout: the point estimates barely move (pooled +0.24 to +0.26), but only 5 of 7 cases
  keep a pair. The pooled and Sonnet 4.6 CIs then include 0 (pooled [-0.04, +0.56]). Haiku 4.5
  holdout was not significant before and is not now.
- Dropping only the strong-evidence runs leaves every conclusion as it was (holdout pooled
  +0.21 [+0.00, +0.43]).

Conclusion: no sign changes. The dev result is robust. The holdout gain is directionally the
same but loses significance once flagged runs are dropped, because the flags remove most of the
holdout pairs. Read the holdout delta as weaker evidence than the all-runs CI suggests.
