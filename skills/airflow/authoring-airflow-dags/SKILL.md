---
name: authoring-airflow-dags
description: >-
  Writes, changes and fixes Apache Airflow DAG code (DAGs, tasks, sensors,
  deferrable operators and triggers, schedules, config-driven DAG factories;
  2.x or 3.x) so it imports, runs and processes the right dates. Use when the
  user asks to add or build an Airflow DAG or pipeline, add a task, sensor or
  schedule, make a sensor deferrable, or fix a DAG: "add a DAG that loads X
  every morning", "my DAG won't show up / has an import error", "KeyError:
  'logical_date'", "fails when I trigger it manually", "processes the wrong
  day", "run at 6am New York on business days", "reruns duplicate rows", "wait
  for the vendor file", "timeout resets on retry", "DAG factory is slow / DAGs
  vanish". Applies whenever a dags/ folder or Airflow project is involved,
  even if the user says only "pipeline" or "job". Not for porting 2.x DAGs to
  Airflow 3 or fixing breakage caused by that upgrade (use
  migrating-to-airflow-3), not for writing a DAG test suite (use
  testing-airflow-dags), and not for dbt models or warehouse query tuning.
license: MIT
compatibility: >-
  Python 3.10+ with apache-airflow 2.x or 3.x installed (the project's env).
  Bundled scripts are stdlib-only and run with that env's Python.
metadata:
  author: altimate-ai
  version: "0.2.0"
---

# Authoring and fixing Airflow DAGs

What goes wrong most often when an agent writes or repairs DAG code:

1. **Wrong-version idioms.** Airflow 3 moved the authoring API and changed defaults and runtime
   behaviour (manual runs without dates, `Variable.set` takes only strings). Code that looks right
   fails only at run time.
2. **Wrong dates.** On 3.x a cron string no longer means "process the previous period", and manual
   runs have no logical date. Nothing errors; the DAG just processes the wrong day.
3. **Verifying too little.** One import error hides the next. One green `dags test` hides what
   breaks on the second run, on a retry, or after a manual trigger in between.

The fix: check the version, write down which period each run processes, and verify in a loop
with the bundled scripts. `<skill-dir>` means the directory this SKILL.md was loaded from.

**Read the matching reference before writing code:**
- `references/dates-and-schedules.md`: whenever the DAG deals with dates, schedules, timezones,
  catchup, backfill, or manual or asset-triggered runs.
- `references/deferrable-and-sensors.md`: whenever you add or change a sensor, make anything
  deferrable, write a trigger, or a `timeout`, retry or `soft_fail` rule matters.
- `references/dag-factories.md`: whenever one file builds many DAGs or tasks from config, or the
  problem is parse time, DAGs that vanish or appear half-built, new DAG versions on every parse,
  or pools and priorities across DAGs.

## Workflow

Copy this checklist into your notes and tick it off:

```
- [ ] 0. Airflow version detected (and which Python/venv has it)
- [ ] 1. Existing DAGs read: conventions, paths, connections, operator types; matching reference read
- [ ] 2. Period contract written: what each run type (scheduled / manual / rerun / backfill) processes
- [ ] 3. Code written or fixed; every task returns only a path/id/count/small aggregate
- [ ] 4. airflow_check.py re-run after EVERY change until exit 0 and next_runs match the contract
- [ ] 5. Executed: dags test / manual_run.py; replay_runs.py (>= 3 runs) if any state crosses runs
- [ ] 6. Rerun of the same period checked for idempotency (for anything that writes data)
- [ ] 7. Report: verified vs not verified
```

### Step 0: detect the Airflow version

Stop when two sources agree: `python -c "import airflow; print(airflow.__version__)"` in the
project's venv (`.venv/`, `venv/`, `$VIRTUAL_ENV`, `which airflow`); pins in `requirements*.txt`,
`pyproject.toml`, `constraints*.txt`, lock files; the `Dockerfile` base image; existing DAG imports
(weak evidence: a repo may be mid-upgrade). If pin and install disagree, target the pin and say so.
Everything below branches on the major version:

| | Airflow 2.x | Airflow >= 3.0 |
|---|---|---|
| DAG/task API | `from airflow.decorators import dag, task`; `from airflow import DAG` | `from airflow.sdk import dag, task, DAG, Variable, Param, get_current_context` |
| Core operators/sensors | `airflow.operators.bash`, `airflow.operators.python`, `airflow.sensors.filesystem` | `airflow.providers.standard.operators.bash` / `.python` / `.empty`, `airflow.providers.standard.sensors.filesystem` |
| Timetables | `airflow.timetables.trigger.CronTriggerTimetable`, `airflow.timetables.interval.CronDataIntervalTimetable` | 3.2+: `from airflow.sdk import CronTriggerTimetable, CronDataIntervalTimetable`; 3.0/3.1: the 2.x paths |
| Schedule kwarg | `schedule=` (2.4+); `schedule_interval` deprecated | only `schedule=`; `schedule_interval`, `timetable`, `concurrency` are TypeErrors |
| `catchup` default | True (backfills every missed interval on deploy) | False |
| Cron string / `timedelta` schedule | interval timetable: run fires at period end, `ds` = period start | trigger timetable: `ds` = the day the run fires, zero-width interval |
| Manual run | always has a logical date (default now) | usually `logical_date`, `ds`, `data_interval_*` are **absent** |
| Removed context keys | available | `execution_date`, `next_ds`, `prev_ds`, `yesterday_ds`, `tomorrow_ds`... gone |
| Metadata DB in tasks | works (discouraged) | blocked: no `create_session`, `DagRun.find`, ORM queries |
| `Variable.set(k, v)` | any value is str()-ed | `v` must be `str` (int/float/dict raise `ValidationError`); or `serialize_json=True` |

Never guess an import path: run `python -c "from X import Y"` in the project env. A module that
"should" exist is the most common hallucination, and it only shows up as an import error.

### Step 1: read before writing

Read one or two existing DAGs and match them: import style, `default_args`, tags, how they build
file paths, connection ids, table names, output layout. Keep the operator types the user named or
the project already uses (a Bash report stays a `BashOperator`). Add tasks only when the request
needs them. Task code does not run with the project root as its working directory
(`BashOperator` runs in a temporary directory), so derive paths from `Path(__file__)` or the
convention the existing DAGs use, never from a bare relative path. Print the header of every
input file (`head -3`) before writing code that selects its columns. Then read the reference
that matches the task (list above).

### Step 2: write the period contract

Before touching dates, write one line per run type, in the business timezone:

```
scheduled run firing Tue 06:00 America/New_York -> processes Mon (previous business day)
manual trigger (3.x, no logical date)            -> same rule applied to the trigger time (run_after)
rerun / clear of any run                          -> processes the same period as the original run
backfill of date D                                -> processes the same period as the scheduled run for D
```

Take the period from the user's words, not from a template. "For the run's date", "that day",
"that day's file" and "for its logical date" mean the run's own day. That needs a trigger
timetable (the 3.x default for a cron string), and the day comes from `logical_date` (or
`run_after` on a manual run): `airflow dags test <dag> 2026-09-28` must write the 2026-09-28
output. Use a data-interval timetable only when the run processes the period that just ended
("yesterday's data at 3am"). "Yesterday", "the previous day" and "the previous business day"
mean one period earlier. When fixing a DAG and the request names no period, the contract is what
the existing code already processes on this Airflow version (for a scheduled run, the day its
`ds` renders). A fix that silently shifts outputs by a day is a new bug. Implement the contract
once, in one helper, and use it from every task and template.

Use the verified `run_window()` helper from `references/dates-and-schedules.md`: `prev=lambda d: d`
for the run's own day, `prev=prev_business_day` for the previous business day. The key rules:

- **Make the timetable explicit on 3.x** when the period matters: `CronTriggerTimetable(cron,
  timezone=tz)` means "run at this time", and you compute the period. `CronDataIntervalTimetable`
  keeps the 2.x "the run processes the interval that just ended" behaviour.
- **Never derive the processed day from the wall clock** (`datetime.now()`, `date.today()`,
  `pendulum.now()`, `CURRENT_DATE`) or from `dag_run.start_date`. A retry, clear or backfill then
  processes the wrong day.
- **3.x manual runs**: the day comes from `dag_run.logical_date or dag_run.run_after`, converted
  with `pendulum.instance(...)` to UTC (or to the business timezone the contract names), never to
  the worker's local timezone. Never use `run_after` alone: for `dags test <dag> D`, backfills and
  triggers with a date, it is the creation time.
- **Templates break too.** `{{ ds }}`, `{{ ds_nodash }}`, `{{ data_interval_start }}` raise
  `UndefinedError` on a 3.x manual run. Replace them with a value the date helper produced (XCom,
  or a `user_defined_macros` function). Grep every templated field and `.sql`/`.sh` file.
- **Local business time**: `CronTriggerTimetable("0 6 * * 1-5", timezone="America/New_York")`.
  Never approximate it with a shifted UTC cron, which drifts by an hour at every DST change.
- **Half-open windows**: `start <= ts < end`. **`start_date`**: a fixed `pendulum.datetime(...,
  tz=...)`. Set `catchup` explicitly ("must not backfill on deploy" = `catchup=False`, on 2.x too).

### Step 3: write the code (defaults)

**Parse time is not run time.** The DAG processor imports every DAG file every few seconds, in a
process with no access to task secrets. Anything at module level, in a `with DAG` block, in a
`@dag` function body, or in default arguments runs at parse time. Keep it declarative and
deterministic:

- `Variable.get`, `BaseHook.get_connection`, DB connections and HTTP calls go **inside a task**,
  or into a templated field (`{{ var.value.name }}`, `{{ conn.my_conn.host }}`). Whether a
  parse-time lookup works depends on where the file is parsed: on 3.3, `airflow dags test` failed
  with `VARIABLE_NOT_FOUND` for a Variable that existed.
- No `now()`, `random`, `uuid` or `hash()` in DAG arguments, ids, docs or schedules. Each parse
  then builds a different DAG and creates a new DAG version (`hash()` is salted per process).
- Tasks generated from a list or config: build it as `sorted(set(items))`, or
  `list(dict.fromkeys(items))` to keep file order. A `set` iterates in a different order in each
  process, and a duplicate entry raises `DuplicateTaskIdFound`. Read the list from a file deployed
  with the DAGs, not from a service. For factories, see `references/dag-factories.md`.
- Heavy imports (pandas, cloud SDKs) inside the task function.

**TaskFlow parameters must not be named like context keys** (`ds`, `logical_date`, `params`,
`ti`, `dag_run`...). `.expand()`/`.partial()` on such a parameter fails at import, and on 2.x a
positional value fails with a "reserved" error. Parameters named after removed 3.x keys
(`execution_date`, `prev_ds`) silently stay `None`. Read context with `**context` or
`get_current_context()`.

**Idempotent writes (default pattern).** Key every write on the run's window and replace that
partition in one transaction, so a retry after a half-finished attempt repairs the day:

```python
con.execute("BEGIN")
con.execute("DELETE FROM target WHERE business_day = ?", [day])
con.execute("INSERT INTO target SELECT ... WHERE ts >= ? AND ts < ?", [start, end])
con.execute("DELETE FROM target_summary WHERE business_day = ?", [day])   # rollups too:
con.execute("INSERT INTO target_summary SELECT ... WHERE business_day = ?", [day])  # recompute, never append
con.execute("COMMIT")
```

`MERGE`/upsert on a real key, or `INSERT OVERWRITE ... PARTITION`, is equivalent. "Skip if
already loaded" and "insert only missing ids" are not: they never repair a partial or stale day.
For files, write the whole day's file (to a temp name, then rename); never append.

**Large data between tasks: claim check.** A TaskFlow return value is an XCom row in the metadata
DB, meant for small values (ids, paths, counts). A task that reads raw input writes its output to
storage at a path keyed on the run's window and returns the path. Returning rows, records, a
DataFrame or a dict of rows is the same mistake. Size it at the volume the user expects. On 3.x,
`xcom_pull()` without `task_ids` returns only the current task's XCom, and values must be
JSON-serialisable.

**State carried between runs** (watermarks, cursors, "only new rows since last run"). On 3.3,
`xcom_pull(..., include_prior_dates=True)` returned a single value when one earlier run matched,
and a **list in no date order** when several did. A retry (2.x and 3.x) or rerun clears that task's
own XComs first. Prefer a state table or file keyed by DAG and period, or derive the window from the run's
dates. If you do use prior XComs, select the latest explicitly. Either way, run >= 3 consecutive
runs (step 5).

**Sensors and deferrable tasks.** Never leave a long wait in `poke` mode with the default 7-day
`timeout`. Use `mode="reschedule"` or `deferrable=True` with an explicit `timeout` in seconds.
Point file sensors at the exact file for the run's day. Before writing a trigger, deferrable
operator, or retry/timeout/soft_fail logic, **read `references/deferrable-and-sensors.md`**.

**BashOperator scripts.** Use an absolute path. A `bash_command` ending in `.sh` is treated as a
Jinja template file and fails with `TemplateNotFound` unless it is on the template search path.
Put arguments after the script (`bash /abs/path/publish.sh 2026-03-09`) or end with a space.

## Step 4: verify until clean

Run the checker with the project's Airflow Python after **every** change, not once at the end:

```bash
python <skill-dir>/scripts/airflow_check.py dags/            # text report
python <skill-dir>/scripts/airflow_check.py dags/ --dag-id my_dag --from 2026-03-06 --runs 5 --json
```

It parses the DAGs with a real DagBag (throwaway metadata DB), previews the next runs with the
scheduler's own timetable code, and runs version-aware static rules. Exit codes: 0 clean
(warnings allowed), 1 import error, 2 error-severity finding, 3 usage/environment problem.

1. Fix the first import error or error finding, then re-run. A file that failed to import hid
   every later problem in it, so new errors after a fix are normal.
2. Repeat until exit 0. Read every warning and either fix it or state why it does not apply.
3. Compare `next_runs` with the period contract: timezone, weekdays, and what
   `data_interval_*`/`logical_date` mean. Exit 0 does not prove the schedule is right.

## Step 5: execute the DAG (one run, then several)

When an Airflow environment exists, run the DAG. A clean parse does not prove the tasks work:
removed context keys, templates, wrong paths, `Variable.set` types and retry logic fail only at
run time. **Never hand back code whose run you did not watch succeed.**

```bash
airflow db migrate                                     # once per fresh AIRFLOW_HOME (for dags test)
airflow dags test <dag_id> 2026-03-09T06:00:00+00:00   # use a real scheduled tick from next_runs
python <skill-dir>/scripts/manual_run.py <dag_id> --run-after 2026-03-10T00:30:00Z   # 3.x manual trigger
python <skill-dir>/scripts/replay_runs.py <dag_id> --from 2026-03-09 --runs 3 \
    --manual 2026-03-10T09:30:00Z --rerun 1 --show-xcom                            # consecutive runs
```

- Pass a real tick from the preview as the date and inspect the outputs (file names, row counts,
  the day inside the data). `dags test <dag_id>` **without** a date is not a 3.x UI trigger; use
  `manual_run.py` (`logical_date=None`, exactly like a trigger with an empty date field).
- **Run `replay_runs.py` with `--runs 3` or more whenever** the DAG carries state from one run to
  the next (a watermark, cursor, counter or Variable it updates), reads prior XComs
  (`include_prior_dates`), reads the previous run's output, or uses `depends_on_past`. It runs N
  consecutive scheduled runs (the scheduler's dates and intervals), optional manual runs and
  reruns, against ONE throwaway metadata DB, each in its own process, printing one JSON line per
  run (state, task_states, failed_tasks, duration_s, xcom). Exit 0 = all succeeded, 2 = a run
  failed or hung. Then check what the second and third runs processed, not just their state.
- Run the same period twice (`--rerun 1`) and confirm identical outputs (no duplicate rows).
- Retries: set a short `retry_delay` and force one failure (a stub that fails once); both
  `dags test` and `replay_runs.py` run real retries.
- Stub inputs with `AIRFLOW_VAR_<NAME>=...` / `AIRFLOW_CONN_<ID>='{"conn_type": ...}'` env vars.
  An env Variable shadows the DB, so a task's `Variable.set` is invisible to the next run; use
  `--var` for Variables the DAG updates.
- A sensor waits in real time up to its `timeout`. Create the awaited file first, or the test
  blocks. `dags test` runs triggers inline but does not enforce `defer(timeout=)`.

If no Airflow environment is available, say so and stop at the static checks. Do not claim the
DAG runs.

## Gotchas

- `ds` and `{{ ds }}` render the **UTC** date. A 22:00 New York run gets the next calendar day.
- `dag_run.logical_date`, `run_after` and `data_interval_*` are stdlib `datetime`. Wrap them in
  `pendulum.instance()` before `.in_tz()`, `.subtract()` or `.start_of()`. `run_after` does not
  exist on 2.x.
- A 3.x scheduled run's `run_id` is named after `run_after`, not the logical date. Never parse
  dates out of `run_id`.
- On 3.x, triggering with an explicit logical date under an interval timetable processes the
  interval before the trigger time. To reprocess day D, use a `params={"day": ...}` override or
  `airflow backfill create` (2.x: `airflow dags backfill`).
- `catchup=True` runs start concurrently (default `max_active_runs` is 16). Set
  `max_active_runs=1` when a run depends on the previous run's output.
- Removing a parse error by deleting the offending argument changes behaviour. Translate it:
  `schedule_interval="0 6 * * *"` becomes `schedule="0 6 * * *"`, not `@daily`, and not removed.
- A `try/except` around a `with DAG(...)` block still registers the half-built DAG; invalid crons
  and cycles fail the whole file later, and `dag.validate()` skips the cycle check (3.x: call
  `dag.check_cycle()`; 2.x: `airflow.utils.dag_cycle_tester.check_cycle(dag)`). See
  `references/dag-factories.md`.

## Report

Finish with a short report the user can trust:

```
Airflow version: 3.3.2 (from requirements.txt; installed env matches)
Changed: dags/x.py (what and why, one line each)
Period contract: scheduled -> ..., manual -> ..., rerun -> ...
Verified:
  - airflow_check.py: exit 0, 0 import errors, warnings: <list or none>; next_runs match the contract
  - airflow dags test x 2026-03-09T06:00Z: success; output/... has N rows for 2026-03-06
  - replay_runs.py --runs 3 --manual ... --rerun 1: all success; run 2 read run 1's watermark
Not verified: <e.g. real triggerer restarts, real warehouse connection, holidays>
```

Only list something under "Verified" if you ran it in this session and saw the result.
