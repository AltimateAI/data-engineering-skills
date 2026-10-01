---
name: migrating-to-airflow-3
description: >-
  Upgrades existing Apache Airflow 2.x DAG projects (DAGs, plugins, .sql/.sh
  templates, tests) to Airflow 3.x so every scheduled, manual and
  dataset-triggered run writes the same outputs as before. Use when the user asks
  to migrate, port, upgrade or "get these DAGs working on Airflow 3" (3.0 ...
  3.3), when a 2.x repo must run on a new 3.x cluster, or when DAGs broke or
  changed output after an Airflow 3 upgrade: schedule_interval TypeError,
  execution_date/next_ds/tomorrow_ds/conf undefined, Dataset/DatasetAlias to
  Asset, triggering_dataset_events, xcom_pull(include_prior_dates) returning a
  list or None, metadata-DB session blocked, manual or CLI-triggered runs
  failing, SLA pages stopped, reports shifted by one day or week. Works offline
  in the project's own env. Not for writing new DAGs or fixing a DAG unrelated to
  an upgrade (use authoring-airflow-dags), not for writing a DAG test suite from
  scratch (use testing-airflow-dags), and not for dbt models (dbt skills) or
  Snowflake query tuning (snowflake skills).
license: MIT
compatibility: >-
  Python 3.10+ with apache-airflow installed (the 3.x target env; a 2.x env is
  optional). ruff >= 0.13 recommended for the AIR3 rules. Scripts are stdlib-only.
metadata:
  author: altimate-ai
  version: "0.2.0"
---

# Migrating Airflow 2.x projects to 3.x

A migration is done when the 3.x code **imports, runs, and writes the same outputs
as the 2.x code did, for every kind of run the project has**: scheduled runs (the
3rd as well as the 1st), runbook/manual triggers, asset-triggered runs. Import-clean
is not enough. Airflow 3 changed what a bare cron string, a `timedelta` schedule and
a missing `catchup` mean, what a manual trigger carries, and what several runtime
APIs return, and none of that raises an error at import. A plain
`execution_date -> logical_date` rename shifts every output by one period.

`SKILL_DIR` below is the directory containing this file. Run the scripts with the
project's Airflow Python (`python` inside the project venv), not a system Python.

## Step 0: detect versions (source and target)

Read `requirements*.txt` / `pyproject.toml` / lockfile / Dockerfile for the pinned
`apache-airflow`, and run `python -c "import airflow; print(airflow.__version__)"`
in the env you will verify with. Record source (repo pin, 2.x) and target
(installed 3.x), and whether a 2.x env exists anywhere (it gives a real BEFORE).
Check whether the old deployment overrode `catchup_by_default`,
`create_cron_data_intervals` or `create_delta_data_intervals` (airflow.cfg /
`AIRFLOW__SCHEDULER__*`); if not, 2.x defaults were all True.

Deadline Alerts need >= 3.1. `airflow.sdk` imports need >= 3.0; the timetable,
Deadline and `conf` exports from `airflow.sdk` need >= 3.2 (on 3.0/3.1 use the 2.x
`airflow.timetables.*` paths).

## Workflow (copy this checklist and tick it off)

```
- [ ] 1. Inventory: DAGs, plugins/, template files, tests, pins, README runbook (how is each DAG triggered?)
- [ ] 2. Snapshot the untouched project, ruff AIR3 --fix, BEFORE preview
- [ ] 3. Checker findings + per-file edit plan (schedules, catchup, keys, runtime traps)
- [ ] 4. Edits applied, one pass per file
- [ ] 5. Verify loop: checker 0 import errors / 0 errors; ruff AIR on dags/ AND plugins/
- [ ] 6. AFTER preview == BEFORE preview (compare_previews.py exit 0)
- [ ] 7. BEFORE/AFTER replay: >=3 scheduled runs + each runbook trigger, outputs identical
- [ ] 8. Project tests + requirements updated and passing
- [ ] 9. Migration report
```

Turn budget matters on multi-DAG repos: read every DAG, plugin and template once,
write the full per-file plan, then edit each file in one pass. Don't write ad-hoc
probes to explore Airflow APIs: the behaviour you need is in this file and
`references/runtime-traps.md`; the replay in step 7 is the proof.

### 1. Inventory
`grep -rn` dags/, plugins/ and template files (`*.sql`, `*.sh`, `*.j2`) for:
`schedule_interval`, `timetable=`, `catchup`, `execution_date`, `_ds`, `next_`,
`prev_`, `conf.`, `sla`, `Dataset`, `triggering_dataset_events`, `outlet_events[`,
`inlet_events`, `xcom_pull`, `include_prior_dates`, `Session`, `provide_session`,
`DagRun`, `Variable.`, `provide_context`, `days_ago`, `macros.`, `AirflowPlugin`.
Removed keys in templates and context lookups never fail at import, only when the
task runs. Read the README/runbook and docstrings for the intended period ("previous
day", "latest closed day", "today") and for **how each DAG is triggered** (schedule,
asset, `airflow dags trigger` with/without `--conf`): that is the behaviour you keep.

### 2. Snapshot, mechanical fixes, BEFORE preview (one block, before any other edit)
```bash
M="${TMPDIR:-/tmp}/mig"; rm -rf "$M" && mkdir -p "$M" && cp -R . "$M/before"   # untouched copy, step 7
ruff check --select AIR3 --preview --fix --unsafe-fixes dags/ plugins/ tests/
AIRFLOW__SCHEDULER__CREATE_CRON_DATA_INTERVALS=True \
AIRFLOW__SCHEDULER__CREATE_DELTA_DATA_INTERVALS=True \
AIRFLOW__SCHEDULER__CATCHUP_BY_DEFAULT=True \
python SKILL_DIR/scripts/airflow_check.py dags --json --runs 5 > "$M/before.json" 2>/dev/null
python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(d['import_errors'] or 'imports ok',[(x['dag_id'],x['timetable'],x['catchup']) for x in d['dags']])" "$M/before.json"
```
- The env vars switch the 2.x scheduler defaults back on for this command (use the
  deployment's values if step 0 found overrides). They only change how bare cron
  strings / presets / `timedelta` and a missing `catchup` are interpreted, so the
  preview shows 2.x run dates using Airflow's own timetable code.
- `import_errors` not empty: apply only mechanical fixes (dead imports,
  `provide_context`, `days_ago`, `airflow.datasets` -> `airflow.sdk` Asset names,
  which ruff flags but does not rewrite) and re-run; leave schedules and dates alone until
  every DAG is captured. Exit 2 (findings) is expected here.
- 2.x env available? Capture there on `$M/before`, without the env vars.

Ruff's "unsafe" fixes are import moves (`airflow.operators.*` ->
`airflow.providers.standard...`, `schedule_interval` -> `schedule`); review them with
`git diff`. Ruff sometimes adds the new import but leaves the old one, now a
`ModuleNotFoundError`; delete it. Ruff does not fix `days_ago()` (use a fixed
`pendulum.datetime(..., tz="UTC")`), `provide_context=True` (delete it), context
parameter names, URI-keyed event accessors, or any semantic issue below.

### 3. Findings ruff misses, and the edit plan
`python SKILL_DIR/scripts/airflow_check.py dags plugins` (exit 0 clean, 1 import
errors, 2 error findings, 3 usage/env). For each file write down every change
before touching it, using these decisions:

**Schedules: keep the 2.x period (default).** Replace a bare cron string / preset
with `CronDataIntervalTimetable` and a bare `timedelta` with
`DeltaDataIntervalTimetable`. Then `logical_date`, `ds` and `data_interval_*` keep
their 2.x values for scheduled runs and the key mapping below is 1:1. On 3.2+
(on 3.0/3.1 import from `airflow.timetables.interval`):
```python
from airflow.sdk import CronDataIntervalTimetable, DeltaDataIntervalTimetable, dag, task

@dag(
    schedule=CronDataIntervalTimetable("30 2 * * *", timezone="UTC"),  # tz of start_date
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=True,   # copy explicit values; a MISSING catchup ran as True on 2.x
)
```
`schedule=None`, `"@once"` and asset schedules need no timetable change. Do this
for every time-scheduled DAG, hourly producers included: asset consumers rebuild
their window from the producers' intervals (runtime-traps section 3).

**catchup:** a DAG with **no** `catchup` argument ran with `catchup=True` on 2.x
(unless the deployment overrode `catchup_by_default`); write `catchup=True`. The
3.x default is False, so history/backfill runs silently stop. "It's the Airflow 2
default to not catch up" is wrong. Explicit values stay as they are.

**Removed context keys** (Jinja, `.sql`/`.sh` files, `context[...]`, callable
parameters), valid once the schedule is an interval timetable:

| 2.x | 3.x |
|---|---|
| `execution_date` | `logical_date` |
| `next_ds`, `next_ds_nodash`, `next_execution_date` | `data_interval_end \| ds`, `\| ds_nodash`, `data_interval_end` |
| `yesterday_ds` / `tomorrow_ds` | calendar ±1 day of `ds` for every cadence: `macros.ds_add(ds, -1)` / `macros.ds_add(ds, 1)` |
| `prev_ds`, `prev_execution_date` | previous schedule **tick**: -1 day daily, -7 weekly, previous month monthly, Friday for a Monday weekday run; irregular crons: `croniter(cron, data_interval_start).get_prev(datetime)` |
| `prev_execution_date_success` | `prev_data_interval_start_success` |
| `triggering_dataset_events` | `triggering_asset_events` (different structure, below) |
| `conf` (templates, context) | `from airflow.sdk import conf`; templates: `user_defined_macros={"conf": conf}` |

On a **manual trigger** all of these were relative to the trigger date on 2.x
(`ds` = trigger date, `prev_ds` = `next_ds` = `ds`); see "Manual runs" below.
In callables, ask for what you use (`def f(data_interval_start, dag_run, ti, **_)`).
A parameter named after a removed key silently stays `None` on 3.x, and a
parameter fed from XCom must not be named like a context key (`ds`, `params`).

**Runtime traps (read `references/runtime-traps.md` when any grep hit applies):**
- **Cross-run XCom:** `ti.xcom_pull(..., include_prior_dates=True)` returns a
  **list of all earlier values from the 3rd run on** (scalar before), in no date
  order. Add `map_indexes=-1` (latest value, both versions); never take `[-1]`.
- **Cross-DAG XCom** (`xcom_pull(dag_id="other", ...)`) matches **this** run's
  `run_id` on 3.x (None unless the ids match): pass `run_id=`, read the other DAG's
  latest output at or before this run's date, or filter asset `inlet_events` by date.
- **Metadata DB in tasks** (`create_session`, `@provide_session`, `DagRun.find`,
  `.query(...)`) raises `RuntimeError` on a 3.x worker but passes `dags test`. Use
  `ti.get_previous_dagrun(state="success")`, `prev_*_success` context keys, XCom
  or a state store. `Variable.set` needs a str (or `serialize_json=True`); `Variable.get(k, default=)`.
- **Assets:** `Dataset`/`DatasetAlias` -> `airflow.sdk.Asset`/`AssetAlias`.
  Accessors take **objects, not URI strings** (`outlet_events[asset]`,
  `triggering_asset_events[asset]`; a str raises TypeError), in plugin operators too.
  Alias-delivered events are listed under the asset **and** under every source
  alias: read them once via `triggering_asset_events[ALIAS]` and `ev.asset.uri`.
- **Asset-triggered runs have no logical date or data interval on 3.x.** On 2.x
  the interval was min..max of the triggering source runs' intervals; rebuild it
  from `ev.source_dag_run.data_interval_*` (helper in the reference).
- **Plugins:** `AirflowPlugin.macros` (`{{ macros.<plugin>.<fn>() }}`) and
  registered custom timetables still work on 3.3; keep them. Move operator/hook
  bases to `airflow.sdk` and fix their context/event usage.

**Manual runs (UI/API/CLI `airflow dags trigger`, runbooks):** on 3.x they have no
`logical_date`, `ds` or data interval (`{{ ds }}` and even
`{{ logical_date or x }}` raise `UndefinedError`); `dag_run.run_after` is the
trigger time and `dag_run.conf`/`params` work. On 2.x the same trigger ran with
`logical_date` = trigger time and the **latest closed interval**. Port by what the
code read: `ds`/`ts` -> `(dag_run.logical_date or dag_run.run_after) | ds`;
`data_interval_*` -> the core timetable's `infer_manual_data_interval(run_after=...)`
(the `airflow.sdk` timetable lacks it); templates ->
`{% set day = ds if ds is defined else (dag_run.run_after | ds) %}`. Never `now()`.
Code: runtime-traps section 4.

**XCom from another task:** `ti.xcom_pull(key=...)` without `task_ids` only looks at
the current task on 3.x and returns `None`. Add `task_ids="<producer>"`.

**SLA:** `sla=` / `sla_miss_callback` are accepted and ignored on 3.x. Rebuild as a
DAG-level deadline on 3.2+ (on 3.1 only `AsyncCallback`, classes from
`airflow.sdk.definitions.deadline`; on 3.0 use `dagrun_timeout` + `on_failure_callback`):
```python
from airflow.sdk import DeadlineAlert, DeadlineReference, SyncCallback
deadline=DeadlineAlert(reference=DeadlineReference.DAGRUN_QUEUED_AT,
                       interval=timedelta(hours=2), callback=SyncCallback(notify)),
```
Use `DAGRUN_QUEUED_AT` for "not finished N hours after the run was queued", not
`DAGRUN_LOGICAL_DATE` (one period before the run fires under an interval timetable,
so already past). The callback takes `(**kwargs)` / `(context=None, **kwargs)`.

### 4. Edit
Apply each file's plan in one write. Keep task ids, dependencies, output paths,
file names and formats unchanged; downstream consumers read them. Name each task
variable like its `task_id` (ruff AIR001), e.g. `publish_report = BashOperator(task_id="publish_report")`.

### 5. Verify loop (do not stop at the first green)
`python SKILL_DIR/scripts/airflow_check.py dags plugins` after EVERY fix until exit
0; fixing one error often uncovers the next. Then
`ruff check --select AIR --preview dags/ plugins/` (all AIR rules): AIR311 means an
old import path, AIR001 a task variable not named like its `task_id`.

### 6. AFTER preview must equal BEFORE
```bash
M="${TMPDIR:-/tmp}/mig"
python SKILL_DIR/scripts/airflow_check.py dags --json --runs 5 > "$M/after.json" 2>/dev/null
python3 SKILL_DIR/scripts/compare_previews.py "$M/before.json" "$M/after.json"
```
Exit 0: same fire times, logical dates, data intervals and catchup. Any diff is a
behaviour change: fix it, or record a deliberate, user-approved change.

### 7. BEFORE/AFTER replay (the proof)
One `dags test` per DAG misses the bugs that matter: the `include_prior_dates`
list appears on run 3, a runbook trigger has no date, state flows between DAGs.
Replay **the same plan** on the untouched copy and on the migrated copy, then diff:
```bash
M="${TMPDIR:-/tmp}/mig"; rm -rf "$M/after" && cp -R . "$M/after"
cat > "$M/plan.txt" <<'EOF'
# producers first; >=3 consecutive scheduled runs each; every runbook trigger as the runbook says
daily_load  --runs 3 --from 2026-03-02
reprocess   --runs 0 --manual 2026-03-05T09:15:00Z --conf '{"day": "2026-03-03"}'
EOF
python SKILL_DIR/scripts/replay_compare.py --before "$M/before" --after "$M/after" \
    --plan "$M/plan.txt" --outputs output --before-python "$PY2"   # or --legacy-before
```
- One metadata DB per side, shared by all plan lines, so XCom/Variables carry over.
  Pass the env the project reads with `--env KEY=VALUE` (`{root}` = that side's
  copy): connections, `AIRFLOW_VAR_*`, `AIRFLOW__<SECTION>__<KEY>` options.
- Run it in the foreground with a long command timeout (a few seconds per planned
  run; both sides in parallel, retries disabled). Exit 0 = same run dates and identical files under
  `--outputs`; exit 2 = a difference, a bug unless the user approved it.
- **No 2.x Python:** `--legacy-before` runs BEFORE on 3.x with the 2.x scheduler
  defaults; first make `$M/before` import on 3.x with import-only edits (the
  step-2 ruff command, `airflow.datasets` -> `airflow.sdk` Asset names), nothing
  else. It reproduces 2.x
  schedule dates; BEFORE runs that fail on removed keys, and manual triggers, have no
  baseline (exit 4, "No baseline" section): check those against the 2.x columns of
  `references/runtime-traps.md` and say so in the report.
- Asset-triggered DAGs cannot be replayed (no events): check them against
  runtime-traps sections 2-3 and report them as not replayed.
- While fixing, `replay_runs.py DAG --runs 3 --manual T` replays one DAG alone.

### 8. Project tests and requirements
- Pin `apache-airflow==<target>`; add `apache-airflow-providers-standard` when the
  code imports `airflow.providers.standard` (match `pip show` of the installed one).
- DagBag tests on 3.x: `from airflow.dag_processing.dagbag import DagBag` (3.2+;
  `airflow.models.dagbag` on 3.0/3.1); `include_examples` is gone on 3.3 (TypeError), set
  `AIRFLOW__CORE__LOAD_EXAMPLES=False`; use `dagbag.dags[id]`, not `get_dag(id)`
  (queries the metadata DB).
- Keep the suite meaningful: it must still fail when a DAG file does not import.
  Don't delete or skip tests to get green.

### 9. Migration report
Versions (source -> target); per DAG each behaviour decision (timetable, catchup,
manual-run handling, asset window, state replacement, SLA -> Deadline); what was
**verified** (checker exit, compare result, replay sequence and diff result, pytest)
versus **not verified** (no 2.x env, asset-triggered runs not replayed, callback not fired).

## Gotchas

- **Same string, different dates.** On 3.x `"0 4 * * *"`, `"@daily"` and
  `timedelta(days=1)` are trigger timetables: `ds` is the day the run fires, not
  the previous period. The most common silent regression.
- **Removed keys fail late or not at all.** Templates fail only when the task
  renders; callable parameters named after removed keys are just `None`.
- **One run proves little.** The 3rd scheduled run, a manual trigger between
  scheduled runs and an asset-triggered batch each hit different code paths.
- **`dags test <dag> <date>` is not a scheduled run**: under an interval timetable
  it uses the interval ending before the date, and it is not a manual trigger either
  (it sets a logical date). Use `replay_runs.py` / `manual_run.py`.
- **`dag_run.*` datetimes are stdlib `datetime`**: wrap with `pendulum.instance()`.
- **`airflow dags test` exits 1 with DeadlineAlert on 3.3.2** (`'dict' object has
  no attribute 'hex'`) after all tasks succeed: an Airflow bug; keep the deadline.

## References (read only when needed)
- `references/runtime-traps.md`: read when the inventory finds `xcom_pull`
  with `include_prior_dates` or `dag_id=`, DB sessions, `Variable.set`, Datasets
  or aliases, asset-scheduled DAGs, runbook/CLI triggers, `conf` or removed keys in
  template files, plugins. Verified 2.11 vs 3.3 behaviour plus replacement code.
- `references/dates-and-schedules.md`: read for non-UTC timezones / business days,
  3.x-native trigger timetables, or reasoning about 2.x periods without any env.
- `scripts/airflow_check.py --help`, `scripts/compare_previews.py --help`,
  `scripts/replay_compare.py --help`, `scripts/replay_runs.py --help`,
  `scripts/manual_run.py --help`.
