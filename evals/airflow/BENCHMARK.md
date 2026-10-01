# Airflow skills benchmark (2026-10-01)

This benchmark tests whether the three Airflow skills (`authoring-airflow-dags`, `migrating-to-airflow-3`,
`testing-airflow-dags`) help an agent produce **working** Airflow code. The final campaign used
**Claude Code 2.1.286 with Claude Sonnet 5.5 and Claude Opus 5.5**, in two arms (the same set-up with and
without the Airflow skills), on two suites:

- **Hard suite:** 6 whole-project tasks (`hard-*`), 3 runs per case, arm and model.
- **Core suite:** 20 common Airflow tasks, 1 run per case, arm and model.

That is 72 graded runs for the hard suite and 80 for the core suite (Sonnet 5.5 and Opus 5.5 together),
plus a trigger eval. An earlier campaign on altimate-code 0.12.2 with Sonnet 4.6 and Haiku 4.5 (older skill
version) is summarised in section 4.

Read this first:

- The hard suite has **6 cases, of which 2 are holdout**. Everything below about unseen tasks rests on
  those 2 cases (6 runs per model and arm). The confidence intervals are wide.
- The skills were iterated against the dev cases with Sonnet 5.5, so dev numbers are **tuned-on**.
- The hard cases were kept because a Sonnet 5.5 baseline failed them in probing, so **Sonnet 5.5's baseline
  is biased downward**. Opus 5.5 was not used for selection, so its numbers are the fairer read.
- On the core suite, both models are near ceiling without the skills and the skills change little.

A run passes when all of its primary (behavioural) checks pass. The paired delta is the mean over cases of
(skill pass rate - baseline pass rate) for the same case and model. The 95% CI is a percentile bootstrap over
cases (10,000 resamples, seed 0, `evals/harness/report.py`). With 2 cases the bootstrap can only produce a
handful of distinct values, so treat those intervals as rough.

## 1. Headline: hard suite, Claude Code

Pass counts are runs that passed all primary checks over valid runs (every run in this campaign was valid).

| Split | Model | Cases | Baseline | With skills | Paired Δ pass rate [95% CI] | Paired Δ primary score [95% CI] |
|---|---|---|---|---|---|---|
| **holdout** | Opus 5.5 | 2 | 5/6 (83%) | **6/6 (100%)** | +0.17 [0.00, +0.33] | +0.02 [0.00, +0.04] |
| **holdout** | Sonnet 5.5 | 2 | 4/6 (67%) | **6/6 (100%)** | +0.33 [0.00, +0.67] | +0.12 [0.00, +0.23] |
| dev (tuned-on) | Opus 5.5 | 4 | 9/12 (75%) | 12/12 (100%) | +0.25 [0.00, +0.50] | +0.02 [0.00, +0.06] |
| dev (tuned-on) | Sonnet 5.5 | 4 | 5/12 (42%) | 12/12 (100%) | +0.58 [+0.17, +1.00] | +0.16 [+0.04, +0.27] |
| all 6 cases | Opus 5.5 | 6 | 14/18 (78%) | 18/18 (100%) | +0.22 [+0.06, +0.44] | |
| all 6 cases | Sonnet 5.5 | 6 | 9/18 (50%) | 18/18 (100%) | +0.50 [+0.17, +0.83] | |

Pooled over both models (case-clustered bootstrap, a resampled case carries both models' deltas): holdout
+0.25 [+0.17, +0.33] over 4 case-model pairs, dev +0.42 [+0.25, +0.58] over 8, all 6 cases +0.36
[+0.22, +0.50] over 12.

Per case, pass count (mean primary score), baseline → skills, 3 runs each:

| Split | Case | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|
| holdout | `hard-migration-ledger-close` | 1/3 → 3/3 (0.77 → 1.00) | 3/3 → 3/3 (1.00 → 1.00) |
| holdout | `hard-deferrable-debug-partition-sensor` | 3/3 → 3/3 (1.00 → 1.00) | 2/3 → 3/3 (0.96 → 1.00) |
| dev | `hard-deferrable-sensor-retry-budget` | 2/3 → 3/3 (0.71 → 1.00) | 3/3 → 3/3 (1.00 → 1.00) |
| dev | `hard-migration-claims-partitions` | 0/3 → 3/3 (0.75 → 1.00) | 3/3 → 3/3 (1.00 → 1.00) |
| dev | `hard-migration-meter-rollups` | 3/3 → 3/3 (1.00 → 1.00) | 1/3 → 3/3 (0.93 → 1.00) |
| dev | `hard-reliability-factory-fleet` | 0/3 → 3/3 (0.92 → 1.00) | 2/3 → 3/3 (0.98 → 1.00) |

What the data supports:

- **With the skills, both models passed all 36 hard-suite runs.** The skill arm never failed one.
- **Opus 5.5, the fairer read:** 14/18 → 18/18 over the six cases. On the 2 holdout cases it is 5/6 → 6/6,
  which is a single baseline failure (`hard-deferrable-debug-partition-sensor` run 3: the sensor no longer
  deferred). That is consistent with a real effect and equally consistent with noise. The all-6-case
  interval [+0.06, +0.44] excludes zero, but those cases include the tuned-on dev cases.
- **Sonnet 5.5:** the holdout gain is 4/6 → 6/6 (one case, `hard-migration-ledger-close`, 1/3 → 3/3, carries
  it). Its baseline is biased downward by selection (above), so the size of its gain is overstated.
- **What the baselines got wrong** (grader details): Sonnet's `hard-migration-ledger-close` baseline lost the
  third hourly extract (the case plants an `include_prior_dates` XCom cursor that returns a list on 3.x; the grader shows the third run failing), wrote the
  wrong `started_by` audit value (`dag_run.external_trigger` is gone) and produced a different housekeeping
  inventory. On `hard-migration-claims-partitions`, Sonnet's baseline rewrote a provider snapshot that should
  not change and read the wrong directory version. On `hard-reliability-factory-fleet`, baselines left
  half-built DAGs loaded or did not name broken config files in the parse output. Opus's baseline misses were
  a changed `catchup` default on an asset-scheduled DAG (`hard-migration-meter-rollups`, 2 runs, one of which also hit the turn limit), a sensor that stopped deferring, and one unreported config file.
- No hard case regressed for either model.

## 2. Core suite on the latest models

20 cases (13 dev, 7 holdout), 1 run per case, arm and model.

| Model | Baseline | With skills | Paired Δ pass rate [95% CI] | Paired Δ primary score [95% CI] |
|---|---|---|---|---|
| Opus 5.5 | 19/20 (95%) | 19/20 (95%) | 0.00 [-0.15, +0.15] | |
| Sonnet 5.5 | 18/20 (90%) | 19/20 (95%) | +0.05 [0.00, +0.15] | |
| Opus 5.5, holdout (7) / dev (13) | 7/7 → 7/7 / 12/13 → 12/13 | | 0.00 [0.00, 0.00] / 0.00 [-0.23, +0.23] | |
| Sonnet 5.5, holdout (7) / dev (13) | 6/7 → 7/7 / 12/13 → 12/13 | | +0.14 [0.00, +0.43] / 0.00 [0.00, 0.00] | |

Only three cases differ between arms:

| Split | Case | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|
| dev | `authoring-vendor-shipments-etl` | 1/1 → 1/1 | 0/1 → 1/1 |
| dev | `migration-inventory-context` | 0/1 → 0/1 | **1/1 → 0/1 (regression)** |
| holdout | `migration-shipments-assets` | 0/1 → 1/1 | 1/1 → 1/1 |

**Interpretation.** Frontier models already handle the common Airflow tasks in this suite: version-correct
imports, idempotent loads, business-day schedules, parse-time pitfalls, pytest suites. The skills do not
change that, so the paired delta is about zero. The skills' value shows up where behaviour is
version-specific and only visible at runtime (the hard suite: 3.x manual-trigger intervals, XCom return
shapes, asset-schedule defaults, deferrable timeout budgets), and in multi-run verification such as
replaying several runs of a DAG and comparing before/after outputs. With 1 run per case the core suite
cannot resolve differences smaller than about one case.

`migration-inventory-context` fails in 3 of 4 cells on the same primary check: the second day's `change` column
comes out blank instead of the day-over-day difference, so the Airflow 2 output is not reproduced. This is the
trap the case plants (callable parameters such as `prev_ds` are silently `None` on 3.x). Opus's baseline passed
it. Opus's skill-arm run failed it although its final message reported byte-identical output: that check called
the original task functions directly with hand-supplied values rather than replaying 2.11, which likely
explains why it did not catch the blank column (an inference from the final message, not verified in the
event stream). Treat this as one regression in a single run, not as a measured rate.

## 3. Trigger eval (Claude Code)

30 short queries (18 should-fire, 6 per skill, and 12 near-misses such as dbt, Prefect, Dagster, cron,
plain pytest and GitHub Actions), 2 runs per query and model, 4 turns each. A run is a hit when the expected
skill fired. Source: [`results/final-triggers-2026-10-01/REPORT.md`](results/final-triggers-2026-10-01/REPORT.md).
That run also included Fable 5.1; its rows are left out here (see section 7).

| Skill | Sonnet 5.5 recall | Opus 5.5 recall | Both models | Precision | Wrong Airflow skill fired |
|---|---|---|---|---|---|
| authoring-airflow-dags | 7/12 (58%) | 12/12 (100%) | 19/24 (79%) | 100% | 0 |
| migrating-to-airflow-3 | 12/12 (100%) | 12/12 (100%) | 24/24 (100%) | 100% | 0 |
| testing-airflow-dags | 11/12 (92%) | 12/12 (100%) | 23/24 (96%) | 100% | 0 |

- No Airflow skill fired on any of the 48 near-miss runs (0/24 per model).
- All 6 misses were Sonnet 5.5 firing no skill: `author-02` (import error in the UI, run 1), `author-05` (make
  the events job rerun-safe, runs 1 and 2), `author-06` (pass a row count between steps, runs 1 and 2) and
  `test-06` (end-to-end test on sample data, run 1). These queries describe the symptom and do not use
  Airflow vocabulary, which is where a model is least likely to reach for a skill.
- Within the task runs of section 1 and 2, the skill arm used an Airflow skill in every run of both models
  (the per-case reports list the skill used).

## 4. Legacy: altimate-code 0.12.2, Sonnet 4.6 and Haiku 4.5, core suite

An earlier campaign (2026-09-30) ran the 20 core cases, 3 runs per case, in altimate-code 0.12.2 through
Vertex, with an **older version of the skills** (`skills/airflow` sha256 `e03e9d6d…`, not the frozen
version above). Those runs shared `/tmp` between parallel runs, so the contamination scan of the current
harness was applied retroactively
([`results/altimate-code-2026-09-30-summary/`](results/altimate-code-2026-09-30-summary/REPORT.md); manual review
in `REVIEW.md` there). The scan flagged 97 of 240 attempts; manual review found no passing run that used another
attempt's code or output. The one confirmed cross-run interference was an old skill instruction that wrote previews
to fixed shared paths, so parallel skill-arm runs overwrote each other's previews and some passing runs read another
case's preview. Its effect on pass rates is unknown in sign and size (the review judged it more likely to add noise
than to inflate passes). The instruction now uses `$TMPDIR`; the exclusion analysis below is a sensitivity check.

Pass counts, baseline → skill (all runs, then excluding flagged runs), and paired Δ with 95% CI:

| Split | Model | All runs | Excluding flagged runs |
|---|---|---|---|
| holdout (7 cases) | Sonnet 4.6 | 8/21 → 17/21: Δ +0.43 [+0.05, +0.76] | 7/19 → 9/10: Δ +0.33 [-0.17, +0.83] |
| holdout (7 cases) | Haiku 4.5 | 4/21 → 5/21: Δ +0.05 [0.00, +0.14] | 0/10 → 4/13: Δ +0.17 [0.00, +0.50] |
| dev, tuned-on (13) | Sonnet 4.6 | 22/39 → 37/39: Δ +0.38 [+0.15, +0.62] | 14/30 → 16/17: Δ +0.22 [+0.06, +0.39] |
| dev, tuned-on (13) | Haiku 4.5 | 14/39 → 31/39: Δ +0.44 [+0.18, +0.67] | 8/20 → 18/24: Δ +0.43 [+0.09, +0.78] |

Overall, all runs: Sonnet 4.6 30/60 (50%) → 54/60 (90%); Haiku 4.5 18/60 (30%) → 36/60 (60%). The gains on
older and smaller models are large on dev and, for Sonnet 4.6, on holdout. For Haiku 4.5 the holdout gain is
not distinguishable from zero. Excluding flagged runs removes most skill-arm passes (the flags there come from
the fixed-path previews), so that column is a stress test with a known bias, and its holdout intervals include
zero for Sonnet 4.6. Read this next to section 2 with care: the two campaigns differ in runner, skill
version, models and harness isolation, so the comparison cannot isolate model strength. It is consistent with
older and smaller models gaining more on common tasks than the latest models do, not proof of it.

## 5. Cost and time per run (API-equivalent USD)

Runs used subscription plans, so nothing was billed per token. `total_cost_usd` from Claude Code is the
API-equivalent list-price cost. Wall time is the agent's wall clock and excludes grading. Costs include
retried attempts. Cost per passing run is total spend over passing runs.

| Suite | Model | Arm | Mean cost / run | Cost / passing run | Mean wall / run | Total |
|---|---|---|---|---|---|---|
| hard | Sonnet 5.5 | baseline | $0.62 | $1.24 | 604 s | $11.17 |
| hard | Sonnet 5.5 | skill | $0.43 | $0.43 | 316 s | $7.82 |
| hard | Opus 5.5 | baseline | $2.00 | $2.57 | 941 s | $35.99 |
| hard | Opus 5.5 | skill | $1.36 | $1.36 | 695 s | $24.43 |
| core | Sonnet 5.5 | baseline | $0.135 | $0.150 | 59 s | $2.70 |
| core | Sonnet 5.5 | skill | $0.214 | $0.225 | 162 s | $4.28 |
| core | Opus 5.5 | baseline | $0.473 | $0.498 | 267 s | $9.46 |
| core | Opus 5.5 | skill | $0.583 | $0.614 | 309 s | $11.66 |

On the hard suite the skill arm was cheaper and faster per run, and on the core suite it added cost (+58% per
run for Sonnet 5.5, +23% for Opus 5.5) and wall time. A plausible explanation (a hypothesis, not a measured
breakdown) is that baselines on hard cases spend long sessions on runtime failures, while on core cases the
agent reads the skill and runs its verification scripts. The campaign's total for the two models was $79.41 (hard)
plus $28.09 (core), API-equivalent.

## 6. Method

**Arms.** Both arms are identical except for `skills/airflow/`. Both stage a copy of the repo skills (dbt,
Snowflake, Databricks, altimate-code); the skill arm's copy adds the three Airflow skills. The Claude Code
inventories show 29 skills in the baseline arm and 32 in the skill arm.

**Isolation (Claude Code runner).**
- Each attempt gets a fresh `CLAUDE_CONFIG_DIR`, so the host's `~/.claude` settings, hooks, plugins, MCP
  servers, skills and memory never load. `CLAUDE.md` and `AGENTS.md` loading is disabled; MCP is empty.
- Each attempt runs in a fresh git-initialised copy of the case fixture, with its own `TMPDIR`, under a macOS
  `sandbox-exec` profile: writes only to the attempt's scratch dir and the agent venv, reads denied for the
  repo checkout, results, other runs' scratch dirs and the host's Claude Code files, and **signals denied
  except within the same sandbox instance**, so an agent's `pkill` cannot reach the harness, graders or sibling
  runs.
- The agent works in a separate **agent venv** (Airflow 3.3.2 or 2.11.2, Python 3.12) that the harness checks
  against a manifest before and after every attempt and restores if changed. **Graders run in different
  grader venvs** that the agent is never pointed at.
- **Inventory verified from the `system/init` event** of every attempt: expected repo skills present, Airflow
  skills only in the skill arm, no MCP server, no unexpected skill or memory file. A mismatch kills the run and
  stops the campaign. This caught a real problem when the Fable 5.1 baseline resumed under a second
  subscription account: that account provisioned two extra skills (`deep-research`, `workflow-authoring`), the
  check aborted the run, and the campaign stopped there rather than mix inventories.
- A contamination scan and a broad-kill-command detector run on every attempt (see Limitations for what they
  flagged).

**Grading.** Each case's `grade.py` executes the agent's final workspace in real Apache Airflow **3.3.2** or
**2.11.2** (Python 3.12.8): DagBag import, `airflow dags test` with DagRun state read from the DB, output data
compared with values computed from the pristine fixture, timetable and data-interval probes, reruns for
idempotency, replays of scheduled, asset-triggered and CLI-triggered runs against the Airflow 2.11 output, and,
for testing cases, the agent's pytest suite run against hidden planted bugs. Secondary checks (verification
commands run, ruff AIR, deprecations) do not affect pass or fail. The agent's own claims are never trusted.

**Grader validation (self-test, re-run for this report, all 26 cases).** `run_eval.py --self-test --split all
--parallel 4` ran **239 variants with 0 violations**: 26 references and 26 alternate references (all must
pass), 26 untouched fixtures and 161 mutants (all must fail at least one primary check). That is 105 mutants
over the 20 core cases and 56 over the 6 hard cases. Output:
[`results/selftest-final/`](results/selftest-final/selftest.txt).

**Hard-case design.** The hard cases are whole-project tasks with runtime-only traps that pass import and lint
checks and only show up when runs are replayed. Each was probed against a **Sonnet 5.5 baseline**, and only
cases the baseline failed for a genuine reason were kept, so Sonnet 5.5's baseline is biased downward by
construction. Opus 5.5 was not used for selection. Each case ships a reference and an independently written
alternate reference that pass, plus mutants that fail, and the primary checks follow from the prompt and
fixture.

**Dev/holdout blindness.** The skills were written and iterated on dev cases with Sonnet 5.5 only. Skill
writers did not read holdout prompts, fixtures or graders. The core suite has 13 dev and 7 holdout cases; the
hard suite 4 dev and 2 holdout. Holdout is the only generalisation evidence, and dev is reported as tuned-on.

**Statistics.** Pass rates count valid runs only (no run was excluded in this campaign). Timeouts, turn
limits and cost caps count as failures. Paired deltas are per case and model, and CIs bootstrap over cases.

## 7. Limitations

- **Small n.** 6 hard cases, 2 of them holdout, 3 runs each. One run moves a case's pass rate by 33 points,
  and the core suite has 1 run per case. The holdout intervals include zero for both models.
- **Selection bias.** Hard cases were chosen by a Sonnet 5.5 baseline failing them. This inflates Sonnet's
  baseline gap. Case selection was not repeated with Opus 5.5 or with the skills in place.
- **One Airflow target.** All 6 hard cases target Airflow 3.3.
- **Correlated traps.** Several migration cases share the same trap (the XCom `include_prior_dates` cursor
  returning a list on 3.x, manual-trigger intervals), and the skills carry a reference for it
  (`runtime-traps.md`). Their passes are not independent evidence of generalisation across traps.
- **Skills tuned on Sonnet 5.5 dev cases.** Dev numbers are upper bounds.
- **Shared agent venv under `--parallel 4`.** Concurrent attempts share one writable agent venv per Airflow
  version; the harness checks and restores it between attempts, but an install by one run could be visible to
  another until then. The final campaign recorded no agent-venv changes or restores.
- **Resume provenance.** The hard campaigns were resumed several times. The harness did not then check that
  case or skill hashes were unchanged across a resume (it does now). The evidence of no drift is that the
  skills hash in the campaign state file is identical before, during and after, and that every final result
  directory's recorded case hashes equal the current case directories (104 of 104).
- **Single machine, macOS.** Everything ran on one Mac with `sandbox-exec`; nothing was run on Linux CI
  runners. The sandbox profile is macOS-specific.
- **Claude Code version changed mid-campaign.** All Sonnet 5.5 and Opus 5.5 runs reported here
  (`claude_code_version` in every attempt record) ran on **2.1.286**. The CLI auto-updated to 2.1.287 on
  2026-10-01 around 11:01 PT, after those runs; only the Fable 5.1 runs below used 2.1.287.
- **Two subscription accounts.** The campaign moved to a second account when the first reached its weekly
  limit during the Fable runs. The reported Sonnet 5.5 and Opus 5.5 results were all run before that switch.
  Costs are API-equivalent estimates, not billing.
- **Fable 5.1 skipped (partial, not reported).** Partial hard-suite runs exist in
  `results/final-hard-{baseline,skill}-claude-fable-5-1-2026-10-01` and are not used for any conclusion. The
  skill arm finished runs 1-2 and the baseline arm finished run 1; the baseline's run 2 was aborted by the
  inventory check and run 3 never ran, then Fable was dropped from the scope. The trigger eval's Fable rows are
  excluded from section 3.
- **Contamination scan and kill commands flagged many runs.** In the final Sonnet 5.5 and Opus 5.5 runs, 15
  hard-suite and 14 core-suite runs were flagged, and 29 hard-suite and 5 core-suite runs ran a broad
  `pkill`. Inspected flags were the literal `/tmp` fallback in `${TMPDIR:-/tmp}` (written by the migration
  skill), agents addressing their own scratch dir by absolute path, and one Opus run
  (`hard-migration-meter-rollups`, skill arm, run 3, passed) that used the Airflow 2.11 grader venv's
  interpreter. One Sonnet 5.5 skill-arm run (`migration-hourly-pageviews-templates`) mentioned the staged skill
  by a `~/.claude/skills/...` path. Every `pkill` ran under the signal-isolated sandbox, so it could not reach other runs. Not
  every flag was reviewed by hand. Excluding all flagged runs leaves the picture unchanged (hard, baseline →
  skills: Sonnet 5/11 → 15/15, Opus 12/16 → 15/15; core: Sonnet 16/17 → 10/10, Opus 19/20 → 18/19), but it
  leaves few pairs.
- **Regressions with causes.** On the hard suite the skill arm never lost a run. On the core suite, Opus 5.5
  lost `migration-inventory-context` (see section 2): the migrated DAG's `change` column came out blank, and its
  self-check did not replay 2.11. The same case also failed for Sonnet 5.5 in both arms, so the migration skill does not
  reliably close this trap. Skill-arm
  secondary scores matched or exceeded baseline on both suites.
- **Triggering depends on phrasing.** Sonnet 5.5 missed the skill on queries with no Airflow vocabulary
  (section 3); recall is a 4-turn measure.
- **`final.md` content was not evaluated.** Grading never reads the agent's final message.

### Post-benchmark fixes

The benchmarked `skills/airflow` tree hash is recorded in each result's `meta.json` (and below).
The shipped skills tree differs only by these helper fixes and their documentation: version-aware context
keys (including removed `conf`), optional missing `plugins/`, template findings with `--dag-id`, scoped
parse-time checks, timetable identity and interval comparisons, mutation recovery after interrupted runs,
and exit 4 for manual runs without a legacy replay baseline. These fixes were made after the benchmark;
the reported results and numbers have not been changed or rerun against the updated skills.

Agents could also see other processes' command lines through `ps`. A scan of the 152 reported task
transcripts (2,912 tool calls) found no access to solutions, results or cases files. Outside-process argv
access is now blocked through both process-info and `kern.proc` sysctl restrictions; the sandbox also
denies the whole checkout and the evaluation cache, with explicit allowances for each attempt's inputs.

## 8. Reproducibility

| Item | Value |
|---|---|
| Agent | Claude Code 2.1.286 (`--runner claude-code`), models `claude-sonnet-5-5`, `claude-opus-5-5` |
| Airflow 3.3 env | apache-airflow 3.3.2, Python 3.12.8, pytest 9.1.1, ruff 0.16.9, duckdb 1.5.6, pandas 3.0.5 |
| Airflow 2.11 env | apache-airflow 2.11.2, Python 3.12.8 |
| Host | macOS 26 arm64, single machine |
| Benchmarked `skills/airflow` sha256 | `d3af9fac9ff0337042ffb634539cd96828c2f63020d1651fee7fe70fd09557a0` (identical in the campaign state file before and after the campaign and in every skill-arm `meta.json`; computed by `run_eval.hash_dir`, bytecode ignored; shipped helper fixes are listed above) |
| Staged skills sha256 | baseline `ca2b482d…`, skill `45fa68a5…` |
| Runs | 2026-10-01 09:29-16:02 UTC (Sonnet 5.5 and Opus 5.5 final runs) |
| Results | `results/final-{hard,core}-{baseline,skill}-claude-{sonnet,opus}-5-5-2026-10-01`, merged in `results/final-summary-2026-10-01/{hard,core}/` |
| Triggers | `results/final-triggers-2026-10-01/` |

```bash
evals/harness/setup_envs.sh
PY=~/.cache/des-evals/airflow-3.3/bin/python
$PY evals/harness/run_eval.py --cases evals/airflow/cases --self-test --split all --parallel 4 \
    --out evals/airflow/results/selftest-final
# one arm, one model, hard suite (set CLAUDE_CODE_OAUTH_TOKEN or EVAL_CLAUDE_TOKEN_CMD first)
$PY evals/harness/run_eval.py --runner claude-code --cases evals/airflow/cases --arm skill \
    --models claude-sonnet-5-5 --runs 3 --parallel 4 --split all \
    --case hard-migration-ledger-close --case hard-deferrable-debug-partition-sensor \
    --case hard-deferrable-sensor-retry-budget --case hard-migration-claims-partitions \
    --case hard-migration-meter-rollups --case hard-reliability-factory-fleet \
    --out evals/airflow/results/final-hard-skill-claude-sonnet-5-5-2026-10-01
# repeat with --arm baseline; core suite = the 20 non-hard cases, --runs 1
$PY evals/harness/report.py evals/airflow/results/final-hard-baseline-claude-sonnet-5-5-2026-10-01 \
    evals/airflow/results/final-hard-skill-claude-sonnet-5-5-2026-10-01 \
    evals/airflow/results/final-hard-baseline-claude-opus-5-5-2026-10-01 \
    evals/airflow/results/final-hard-skill-claude-opus-5-5-2026-10-01 \
    --out evals/airflow/results/final-summary-2026-10-01/hard
```

Full per-arm rows are in `results/final-summary-2026-10-01/{hard,core}/REPORT.md` and `results.json`.
