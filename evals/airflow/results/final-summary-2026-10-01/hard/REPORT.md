# Airflow skill eval report

Pass rate = fraction of valid runs whose primary checks all passed. Excluded runs (infra_error, grader_error, skipped_budget) are listed but not counted.

## dev: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | claude-opus-5-5 | 12 (12) | 75% | 0.976 | 0.833 | 0% | 3.4e+06 | 2.13 | 989 | {'ok': 9, 'task_fail': 2, 'turn_limit': 1} |
| baseline | claude-sonnet-5-5 | 12 (12) | 42% | 0.844 | 0.75 | 0% | 1.53e+06 | 0.665 | 603 | {'task_fail': 7, 'ok': 5} |
| skill | claude-opus-5-5 | 12 (12) | 100% | 1 | 1 | 100% | 2.01e+06 | 1.49 | 850 | {'ok': 12} |
| skill | claude-sonnet-5-5 | 12 (12) | 100% | 1 | 0.972 | 100% | 8.2e+05 | 0.452 | 321 | {'ok': 12} |

## dev: paired delta (skill - baseline) over cases

| model | cases | delta pass rate | 95% CI | delta primary score | 95% CI |
|---|---|---|---|---|---|
| claude-opus-5-5 | 4 | 0.25 | (0.0, 0.5) | 0.0237 | (0.0, 0.0556) |
| claude-sonnet-5-5 | 4 | 0.583 | (0.1666, 1.0) | 0.156 | (0.0416, 0.2709) |
| pooled (8 case x model pairs) | 4 | 0.417 | (0.25, 0.5833) | 0.09 | (0.0445, 0.1354) |

Pooled CI: bootstrap over cases; a resampled case carries the deltas of all its models.

## dev: per case

| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| hard-deferrable-sensor-retry-budget | authoring | baseline | claude-opus-5-5 | 3 (3) | 100% | 1 | 1 | - | 1.99 | {'ok': 3} |
| hard-deferrable-sensor-retry-budget | authoring | baseline | claude-sonnet-5-5 | 3 (3) | 67% | 0.708 | 0.667 | - | 0.302 | {'task_fail': 1, 'ok': 2} |
| hard-deferrable-sensor-retry-budget | authoring | skill | claude-opus-5-5 | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 1.24 | {'ok': 3} |
| hard-deferrable-sensor-retry-budget | authoring | skill | claude-sonnet-5-5 | 3 (3) | 100% | 1 | 0.889 | {'authoring-airflow-dags': 3} | 0.399 | {'ok': 3} |
| hard-migration-claims-partitions | migration | baseline | claude-opus-5-5 | 3 (3) | 100% | 1 | 0.667 | - | 2.53 | {'ok': 3} |
| hard-migration-claims-partitions | migration | baseline | claude-sonnet-5-5 | 3 (3) | 0% | 0.75 | 0.667 | - | 0.607 | {'task_fail': 3} |
| hard-migration-claims-partitions | migration | skill | claude-opus-5-5 | 3 (3) | 100% | 1 | 1 | {'migrating-to-airflow-3': 3} | 2.34 | {'ok': 3} |
| hard-migration-claims-partitions | migration | skill | claude-sonnet-5-5 | 3 (3) | 100% | 1 | 1 | {'migrating-to-airflow-3': 3} | 0.491 | {'ok': 3} |
| hard-migration-meter-rollups | migration | baseline | claude-opus-5-5 | 3 (3) | 33% | 0.926 | 0.667 | - | 3.04 | {'task_fail': 1, 'turn_limit': 1, 'ok': 1} |
| hard-migration-meter-rollups | migration | baseline | claude-sonnet-5-5 | 3 (3) | 100% | 1 | 0.667 | - | 1.51 | {'ok': 3} |
| hard-migration-meter-rollups | migration | skill | claude-opus-5-5 | 3 (3) | 100% | 1 | 1 | {'migrating-to-airflow-3': 3} | 1.32 | {'ok': 3} |
| hard-migration-meter-rollups | migration | skill | claude-sonnet-5-5 | 3 (3) | 100% | 1 | 1 | {'migrating-to-airflow-3': 3} | 0.514 | {'ok': 3} |
| hard-reliability-factory-fleet | debugging | baseline | claude-opus-5-5 | 3 (3) | 67% | 0.979 | 1 | - | 0.944 | {'ok': 2, 'task_fail': 1} |
| hard-reliability-factory-fleet | debugging | baseline | claude-sonnet-5-5 | 3 (3) | 0% | 0.917 | 1 | - | 0.239 | {'task_fail': 3} |
| hard-reliability-factory-fleet | debugging | skill | claude-opus-5-5 | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 1.04 | {'ok': 3} |
| hard-reliability-factory-fleet | debugging | skill | claude-sonnet-5-5 | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 0.403 | {'ok': 3} |

## holdout: by arm and model

| arm | model | runs (valid) | pass rate | primary | secondary | trigger rate | mean tokens | mean cost | mean wall s | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | claude-opus-5-5 | 6 (6) | 83% | 0.982 | 1 | 0% | 2.64e+06 | 1.75 | 844 | {'ok': 5, 'task_fail': 1} |
| baseline | claude-sonnet-5-5 | 6 (6) | 67% | 0.883 | 0.944 | 0% | 1.01e+06 | 0.53 | 607 | {'ok': 4, 'task_fail': 2} |
| skill | claude-opus-5-5 | 6 (6) | 100% | 1 | 1 | 100% | 1.24e+06 | 1.1 | 386 | {'ok': 6} |
| skill | claude-sonnet-5-5 | 6 (6) | 100% | 1 | 0.944 | 100% | 6.56e+05 | 0.4 | 308 | {'ok': 6} |

## holdout: paired delta (skill - baseline) over cases

| model | cases | delta pass rate | 95% CI | delta primary score | 95% CI |
|---|---|---|---|---|---|
| claude-opus-5-5 | 2 | 0.167 | (0.0, 0.3333) | 0.0185 | (0.0, 0.037) |
| claude-sonnet-5-5 | 2 | 0.333 | (0.0, 0.6667) | 0.117 | (0.0, 0.2333) |
| pooled (4 case x model pairs) | 2 | 0.25 | (0.1666, 0.3333) | 0.0676 | (0.0185, 0.1167) |

Pooled CI: bootstrap over cases; a resampled case carries the deltas of all its models.

## holdout: per case

| case | area | arm | model | runs (valid) | pass rate | primary | secondary | skills used | mean cost | statuses |
|---|---|---|---|---|---|---|---|---|---|---|
| hard-deferrable-debug-partition-sensor | debugging | baseline | claude-opus-5-5 | 3 (3) | 67% | 0.963 | 1 | - | 1.23 | {'ok': 2, 'task_fail': 1} |
| hard-deferrable-debug-partition-sensor | debugging | baseline | claude-sonnet-5-5 | 3 (3) | 100% | 1 | 0.889 | - | 0.322 | {'ok': 3} |
| hard-deferrable-debug-partition-sensor | debugging | skill | claude-opus-5-5 | 3 (3) | 100% | 1 | 1 | {'authoring-airflow-dags': 3} | 1.09 | {'ok': 3} |
| hard-deferrable-debug-partition-sensor | debugging | skill | claude-sonnet-5-5 | 3 (3) | 100% | 1 | 0.889 | {'authoring-airflow-dags': 3} | 0.312 | {'ok': 3} |
| hard-migration-ledger-close | migration | baseline | claude-opus-5-5 | 3 (3) | 100% | 1 | 1 | - | 2.26 | {'ok': 3} |
| hard-migration-ledger-close | migration | baseline | claude-sonnet-5-5 | 3 (3) | 33% | 0.767 | 1 | - | 0.738 | {'task_fail': 2, 'ok': 1} |
| hard-migration-ledger-close | migration | skill | claude-opus-5-5 | 3 (3) | 100% | 1 | 1 | {'migrating-to-airflow-3': 3} | 1.11 | {'ok': 3} |
| hard-migration-ledger-close | migration | skill | claude-sonnet-5-5 | 3 (3) | 100% | 1 | 1 | {'migrating-to-airflow-3': 3} | 0.488 | {'ok': 3} |

## Failure classes (all runs)

{'ok': 59, 'task_fail': 12, 'turn_limit': 1}

Total spend (all attempts, all dirs): $79.41

## Isolation

Contamination suspects: 15 run(s).
- hard-deferrable-sensor-retry-budget baseline claude-sonnet-5-5 run 1: bash:<tmp>/p (shared-temp), bash:<tmp>/p (shared-temp), bash:<tmp>/p (shared-temp), bash:<tmp>/p (shared-temp)
- hard-migration-ledger-close baseline claude-sonnet-5-5 run 1: bash:~/.cache/des-evals/work/ (work-root), bash:<work>/ (work-root)
- hard-migration-meter-rollups baseline claude-sonnet-5-5 run 1: bash:<tmp>/meter_dropbox (shared-temp)
- hard-deferrable-debug-partition-sensor baseline claude-sonnet-5-5 run 2: bash:<tmp>/pf (shared-temp), bash:<work>/ (work-root), bash:<tmp>/pf (shared-temp)
- hard-reliability-factory-fleet baseline claude-sonnet-5-5 run 2: bash:<tmp>/t.py (shared-temp), bash:<tmp>/t.py (shared-temp), bash:<tmp>/t.py (shared-temp), bash:<tmp>/t.py (shared-temp)
- hard-deferrable-debug-partition-sensor baseline claude-sonnet-5-5 run 3: bash:<work>/ (work-root), bash:<tmp>/p (shared-temp), bash:<tmp>/stub.log (shared-temp), bash:<tmp>/p (shared-temp)
- hard-migration-meter-rollups baseline claude-sonnet-5-5 run 3: bash:<tmp>/meter_dropbox (shared-temp), bash:<tmp>/meter_dropbox (shared-temp), bash:<tmp>/meter_dropbox (shared-temp)
- hard-deferrable-sensor-retry-budget skill claude-sonnet-5-5 run 2: bash:<work>/ (work-root), bash:<work> (work-root)
- hard-migration-claims-partitions skill claude-sonnet-5-5 run 2: bash:~/.cache/des-evals/work/ (work-root)
- hard-migration-ledger-close skill claude-sonnet-5-5 run 3: bash:<tmp>/mig (shared-temp), bash:<tmp>/mig (shared-temp)
- hard-deferrable-sensor-retry-budget baseline claude-opus-5-5 run 1: bash:<tmp> (shared-temp), bash:<tmp> (shared-temp), bash:<tmp> (shared-temp), bash:<tmp> (shared-temp), bash:<tmp> (shared-temp)
- hard-migration-claims-partitions baseline claude-opus-5-5 run 2: bash:<tmp>/mart_before.csv (shared-temp), bash:<tmp>/mart_before.csv (shared-temp)
- hard-migration-claims-partitions skill claude-opus-5-5 run 1: bash:<tmp> (shared-temp)
- hard-deferrable-debug-partition-sensor skill claude-opus-5-5 run 3: bash:<tmp> (shared-temp), bash:<tmp> (shared-temp), bash:<tmp> (shared-temp)
- hard-migration-meter-rollups skill claude-opus-5-5 run 3: bash:~/.cache/des-evals/airflow-2.11/lib/python3 (grader-env), bash:~/.cache/des-evals/airflow-2.11/bin/python (grader-env), bash:~/.cache/des-evals/airflow-2.11/bin/python (grader-env), bash:~/.cache/des-evals/airflow-2.11/bin/python (grader-env)
Broad kill commands (pkill/killall/kill by pattern): 29 run(s).
- hard-migration-claims-partitions baseline claude-sonnet-5-5 run 1: pkill -f "airflow" ; grep -n "Error\|error" ../sched.log | head -8 | cut -c1-250; ps aux | grep -c "[a]irflow"
- hard-migration-ledger-close baseline claude-sonnet-5-5 run 1: pkill -f "airflow" ; sleep 3; pgrep -fl airflow | head -3; rm -rf output; find . -name __pycache__ -not -path "./.git/*"
- hard-migration-meter-rollups baseline claude-sonnet-5-5 run 1: pkill -f "airflow" ; sleep 3; ps aux | grep -c "[a]irflow"; lsof -i :8793 -i :8080 2>/dev/null | head
- hard-deferrable-debug-partition-sensor baseline claude-sonnet-5-5 run 2: cd <work>/final-hard-baseline-claude-sonnet-5-5-2026-10-01-baseline-20261001-033030/hard-deferrable-debug-partition-sens
- hard-migration-ledger-close baseline claude-sonnet-5-5 run 2: pkill -f "airflow standalone"; pkill -f "airflow"; grep -B25 "HTTPStatusError.__init__" $TMPDIR/af.log | cut -c1-220 | h
- hard-migration-meter-rollups baseline claude-sonnet-5-5 run 2: pkill -f "des-evals/agent-airflow-2.11/bin/airflow scheduler" ; pkill -f "airflow tasks run" ; sleep 1; pgrep -fl "agent ; cd ../mt; pkill -f "agent-airflow-3.3/bin/airflow scheduler" 2>/dev/null; echo "(note: that may also match other session
- hard-deferrable-debug-partition-sensor baseline claude-sonnet-5-5 run 3: cd <work>/*/hard-deferrable-debug-partition-sensor-qcythn61/ws && (python tools/catalog_stub.py --publish orders/2026-09 ; cd <work>/final-hard-baseline-claude-sonnet-5-5-2026-10-01-baseline-20261001-040414/hard-deferrable-debug-partition-sens
- hard-migration-claims-partitions baseline claude-sonnet-5-5 run 3: pkill -f "airflow" ; sleep 2
cat > .afhome/env.sh <<E
export AIRFLOW_HOME=$PWD/.afhome AIRFLOW__CORE__PLUGINS_FOLDER=$PW
- hard-migration-ledger-close baseline claude-sonnet-5-5 run 3: export AIRFLOW_HOME=$PWD/.afhome AIRFLOW__CORE__PLUGINS_FOLDER=$PWD/plugins AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags AIRFLOW
- hard-migration-meter-rollups baseline claude-sonnet-5-5 run 3: pkill -u $(id -u) -f "airflow (scheduler|dag-processor|api-server)" 2>&1; sleep 2
export AIRFLOW__CORE__PLUGINS_FOLDER=$ ; pkill -u $(id -u) -f "airflow (scheduler|dag-processor|api-server)" 2>/dev/null; sleep 3
T=<tmp>/metertest; rm -rf $T; m ; pkill -u $(id -u) -f "airflow (scheduler|dag-processor|api-server)" 2>/dev/null; rm -rf $AIRFLOW_HOME/metertest output; 
- hard-deferrable-debug-partition-sensor skill claude-sonnet-5-5 run 1: pkill -f catalog_stub.py; rm -rf .tmp; git status --short
- hard-deferrable-sensor-retry-budget skill claude-sonnet-5-5 run 2: export WS=$PWD TD=$PWD/../tmp/td PATH=~/.cache/des-evals/agent-airflow-3.3/bin:$PATH
pkill -f manifest_stub; export AIRF
- hard-reliability-factory-fleet skill claude-sonnet-5-5 run 2: cat $TMPDIR/claude-501/*/*/tasks/b9d5gb37z.output | cut -c1-300 | head -20; pkill -f h.py; git status --short; ls config
- hard-deferrable-debug-partition-sensor skill claude-sonnet-5-5 run 3: pkill -f "airflow dags test"; cat "<work>/final-hard-skill-claude-sonnet-5-5-2026-10-01-skill-20261001-042421/hard-defer ; pkill -f "port-file .af/port" ; rm -rf .af; git status --short
- hard-deferrable-sensor-retry-budget baseline claude-opus-5-5 run 1: T=$TMPDIR/e2e; pkill -f "airflow standalone"; sleep 5; pkill -f "airflow (scheduler|triggerer|dag-processor|api-server)" ; T=$TMPDIR/e2e; source $T/env.sh; cd $T; pgrep -fl "airflow triggerer" ; airflow dags trigger e2e_partner -r r3 >/dev/nul ; pkill -f "manifest_stub.py"; pkill -f "airflow standalone"; pkill -f "e2e/home" ; sleep 3; pkill -f "airflow triggerer" 
- hard-deferrable-debug-partition-sensor baseline claude-opus-5-5 run 1: pkill -f "airflow dags test" ; T=$(cd ../tmp && pwd); mkdir -p $T/dags; cp -r dags/lake $T/dags/; rm -rf $T/dags/lake/__ ; T=$(cd ../tmp && pwd); P=$(cat $T/p1); rm $T/dags/scratch2.py
cat > $T/dags/scratch.py <<'EOF'
from datetime import date ; pkill -f catalog_stub.py; cd dags && python -c "import lake_ingest, orders_diff; print('dags import ok')" 2>&1 | tail -1
- hard-migration-ledger-close baseline claude-opus-5-5 run 1: cd <work>/final-hard-baseline-claude-opus-5-5-2026-10-01-baseline-20261001-050445/hard-migration-ledger-close-kfdp7306/w ; cd <work>/final-hard-baseline-claude-opus-5-5-2026-10-01-baseline-20261001-050445/hard-migration-ledger-close-kfdp7306/w
- hard-migration-claims-partitions baseline claude-opus-5-5 run 1: pkill -f "des-evals/agent-airflow" ; pkill -f "drive.py"; sleep 3; cd ../tmp/e2e && python3 - <<'EOF'
import pathlib
p = ; cd ../tmp/e2e; pkill -f "drive.py v"; sleep 1; P=$(lsof -t v2/home/airflow.db v3/home/airflow.db v2/home/logs v3/home/lo ; cd ../tmp/e2e; pkill -f "drive.py v2"; sleep 8; pgrep -f "agent-airflow-2.11" | head; V=~/.cache/des-evals/agent-airflow
- hard-migration-meter-rollups baseline claude-opus-5-5 run 1: pkill -f "e2e3" ; pkill -f "airflow scheduler"; pkill -f "airflow dag-processor"; pkill -f "airflow api-server"; sleep 3
- hard-deferrable-sensor-retry-budget baseline claude-opus-5-5 run 2: pkill -f manifest_stub.py; E=$TMPDIR/e2e; WS=$PWD; cat > $E/stubs.sh <<EOF
#!/bin/bash
cd $E
rm -f p_pub p_outpub p_outh ; E=$TMPDIR/e2e; cd $E && for c in api-server scheduler dag-processor triggerer; do kill $(cat $c.pid) 2>/dev/null; done; 
- hard-migration-ledger-close baseline claude-opus-5-5 run 2: T=$(cd ../tmp && pwd); pkill -f "sim.py" ; grep -B30 "not supported between" $T/sim33.log | grep -v "^\s*$" | head -40; 
- hard-migration-claims-partitions baseline claude-opus-5-5 run 2: E=<work>/final-hard-baseline-claude-opus-5-5-2026-10-01-baseline-20261001-062054/hard-migration-claims-partitions-8lab_r
- hard-migration-meter-rollups baseline claude-opus-5-5 run 2: L=$PWD/../tmp; pkill -f "airflow standalone"; sleep 8; pkill -f "airflow (scheduler|api-server|dag-processor|triggerer)"
- hard-deferrable-debug-partition-sensor baseline claude-opus-5-5 run 3: pkill -f catalog_stub.py; export AIRFLOW_HOME=$PWD/.scratch/ah AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags AIRFLOW__CORE__LOAD_
- hard-deferrable-sensor-retry-budget baseline claude-opus-5-5 run 3: sleep 5; cat "$TMPDIR/claude-501/"*/*/tasks/b292mdt47.output | grep -E "^(PASS|FAIL)|Error|Traceback" | head; pkill -f s
- hard-migration-ledger-close baseline claude-opus-5-5 run 3: cd ../tmp; pkill -f "harness.py.*ctl"; sleep 2; mv events3.good events3.log 2>/dev/null; grep -c success events3.log; rm
- hard-migration-claims-partitions baseline claude-opus-5-5 run 3: cd "$PWD"; T=$(cd ..; pwd)<tmp>; pkill -f "airflow standalone"; pkill -f "airflow scheduler"; pkill -f "airflow api-serv ; cd "$PWD"; pkill -f "airflow standalone" 2>/dev/null; sleep 8; pgrep -fl "airflow (scheduler|api-server|dag-processor|tr
- hard-migration-meter-rollups skill claude-opus-5-5 run 1: M=${TMPDIR:-/tmp}/mig; sed -i '' 's/2026-03-04T00:00:00+00:00"/2026-03-04T01:00:00+00:00"/g; s/east_hourly 2026-03-04T01 ; M=${TMPDIR:-/tmp}/mig; python - <<EOF
p="$M/asset_run.sh"; s=open(p).read()
s=s.replace("export AIRFLOW__SCHEDULER__USE_
- hard-migration-claims-partitions skill claude-opus-5-5 run 3: S=<work>/final-hard-skill-claude-opus-5-5-2026-10-01-skill-20261001-071914/hard-migration-claims-partitions-o3ia812h/cla ; pkill -f "e2e.sh"; pkill -f "airflow standalone"; pkill -f "agent-airflow-3.3/bin/airflow"; sleep 2; M="${TMPDIR:-/tmp}/ ; ps -eo pid,command | grep -E "standalone|airflow (scheduler|api-server|dag-processor|triggerer|webserver)" | grep -v gre
Agent env restored after: 0 run(s); restore failed: 0.

## Sources

- `evals/airflow/results/final-hard-baseline-claude-sonnet-5-5-2026-10-01`: arm=baseline models=['claude-sonnet-5-5'] claude-code=2.1.286 started=2026-10-01T09:29:23+00:00 budget={'cap_usd': 2000.0, 'per_run_cap_usd': {'claude-sonnet-5-5': 6.0}, 'spent_usd': 11.1662, 'stopped_early': False}
- `evals/airflow/results/final-hard-skill-claude-sonnet-5-5-2026-10-01`: arm=skill models=['claude-sonnet-5-5'] claude-code=2.1.286 started=2026-10-01T10:06:04+00:00 budget={'cap_usd': 2000.0, 'per_run_cap_usd': {'claude-sonnet-5-5': 6.0}, 'spent_usd': 7.8203, 'stopped_early': False}
- `evals/airflow/results/final-hard-baseline-claude-opus-5-5-2026-10-01`: arm=baseline models=['claude-opus-5-5'] claude-code=2.1.286 started=2026-10-01T12:04:47+00:00 budget={'cap_usd': 2000.0, 'per_run_cap_usd': {'claude-opus-5-5': 12.0}, 'spent_usd': 35.9895, 'stopped_early': False}
- `evals/airflow/results/final-hard-skill-claude-opus-5-5-2026-10-01`: arm=skill models=['claude-opus-5-5'] claude-code=2.1.286 started=2026-10-01T12:35:11+00:00 budget={'cap_usd': 2000.0, 'per_run_cap_usd': {'claude-opus-5-5': 12.0}, 'spent_usd': 24.4297, 'stopped_early': False}
