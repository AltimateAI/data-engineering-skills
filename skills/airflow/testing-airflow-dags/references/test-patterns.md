# Verified test patterns for Airflow DAG projects

Each snippet below passed on Airflow 3.3 and on Airflow 2.11 with the `conftest.py` from SKILL.md
unless a version is named. They use the `dagbag` and `airflow_db` fixtures from that conftest.

## Contents
1. [API differences between 2.x and 3.x](#1-api-differences-between-2x-and-3x)
2. [Integrity and structure](#2-integrity-and-structure)
3. [Schedules: test the runs the scheduler would create](#3-schedules-test-the-runs-the-scheduler-would-create)
4. [Task callables and transforms](#4-task-callables-and-transforms)
5. [Custom hooks and operators with connections and variables](#5-custom-hooks-and-operators-with-connections-and-variables)
6. [End-to-end runs with dag.test()](#6-end-to-end-runs-with-dagtest)

## 1. API differences between 2.x and 3.x
| Need | Airflow 2.x | Airflow >= 3.0 |
|---|---|---|
| DagBag class | `from airflow.models import DagBag` | 3.2+: `from airflow.dag_processing.dagbag import DagBag`; 3.0/3.1: `from airflow.models.dagbag import DagBag` (try the first, fall back) |
| Hide example DAGs | `DagBag(..., include_examples=False)` works | `include_examples` raises `TypeError` on 3.3; set `AIRFLOW__CORE__LOAD_EXAMPLES=False` before importing Airflow (works on every version) |
| Get a DAG from the bag | `bag.dags[dag_id]` | `bag.dags[dag_id]` (`bag.get_dag()` queries the metadata DB on both versions: "no such table: dag" without a migrated DB) |
| Run a whole DAG in-process | `dag.test(execution_date=...)` | `dag.test(logical_date=...)` |
| `dag.test()` prerequisites | migrated metadata DB | migrated metadata DB **and** the DAG file inside `AIRFLOW__CORE__DAGS_FOLDER` (else "dag is not serialized") |
| Hook / operator base classes | `airflow.hooks.base.BaseHook`, `airflow.models.BaseOperator` | `airflow.sdk.BaseHook`, `airflow.sdk.BaseOperator` |
| Variable | `airflow.models.Variable` | `airflow.sdk.Variable` |
| Timetable of a cron-string schedule | `CronDataIntervalTimetable` | `CronTriggerTimetable` (no `.summary` attribute on the SDK object) |
| `dag.tags` | list | set |

Import what the project already imports. When a test must run on both versions, use
`try: <3.x import> except ImportError: <2.x import>`.

## 2. Integrity and structure
```python
EXPECTED_DAGS = {"invoices_daily", "accounts_sync"}  # the DAG ids the repo defines today


def test_no_import_errors(dagbag):
    # import errors and dependency cycles both land here
    assert dagbag.import_errors == {}, "\n\n".join(f"{f}:\n{e}" for f, e in dagbag.import_errors.items())


def test_expected_dags_load(dagbag):
    assert EXPECTED_DAGS <= set(dagbag.dags)   # a DAG that stops parsing disappears silently otherwise


def test_every_task_has_two_retries(dagbag):        # only because the user asked for it
    bad = [(d.dag_id, t.task_id, t.retries) for d in dagbag.dags.values() for t in d.tasks if t.retries < 2]
    assert not bad


def test_billing_pipeline_order(dagbag):
    dag = dagbag.dags["invoices_daily"]
    expected = {"download": set(), "parse": {"download"}, "store": {"parse"}, "notify": {"store"}}
    assert {t: dag.get_task(t).upstream_task_ids for t in expected} == expected


def test_notify_waits_for_download(dagbag):       # "B only after A", with or without tasks in between
    dag = dagbag.dags["invoices_daily"]
    assert "download" in dag.get_task("notify").get_flat_relative_ids(upstream=True)
```
- Per-task attributes (`t.retries`, `t.owner`, `t.pool`) already include `default_args`, and a task-level
  override wins. Checking `dag.default_args` instead misses a task that overrides the value.
- A task's owner defaults to `"airflow"`; `dag.catchup`, `dag.max_active_runs`, `dag.tags` are plain
  attributes.
- For a stated exact order, compare the full `upstream_task_ids` sets. `a in b.upstream_list` still
  passes when an extra edge or a bypass is added.

## 3. Schedules: test the runs the scheduler would create
Comparing cron strings is brittle (`1-5` vs `mon-fri`, a preset vs a timetable object) and says nothing
about timezone. Ask the timetable for its next runs instead. This helper uses the scheduler's own logic,
needs no DB, and returns the time each run fires (`run_after`) on both versions. The conftest in
SKILL.md ships it as the `upcoming_runs` fixture; the standalone form:
```python
from datetime import datetime, timezone


def upcoming_runs(dag, after, n):
    from airflow.timetables.base import TimeRestriction
    tt = dag.timetable
    try:
        from airflow.serialization.encoders import coerce_to_core_timetable  # Airflow >= 3.0
        tt = coerce_to_core_timetable(tt)
    except ImportError:
        pass
    restriction = TimeRestriction(earliest=after, latest=None, catchup=True)
    last, runs = None, []
    for _ in range(n):
        info = tt.next_dagrun_info(last_automated_data_interval=last, restriction=restriction)
        if info is None:
            break
        runs.append(info.run_after)
        last = info.data_interval
    return runs


def test_weekday_0730_utc(dagbag):
    runs = upcoming_runs(dagbag.dags["invoices_daily"], datetime(2026, 3, 2, tzinfo=timezone.utc), 10)
    assert len(runs) == 10
    assert {r.weekday() for r in runs} == {0, 1, 2, 3, 4}           # every weekday, never Sat/Sun
    assert all((r.hour, r.minute) == (7, 30) and r.utcoffset().total_seconds() == 0 for r in runs)
```
- Assert every part of the stated rule: days, time, timezone. A test that checks only the time passes
  on a Sunday-to-Thursday schedule.
- For a local-time rule ("09:00 New York"), convert first (`r.astimezone(ZoneInfo("America/New_York"))`)
  and generate runs across a DST change.
- Use `info.logical_date` / `info.data_interval` from the same loop when the rule is about which period
  a run processes; read [dates-and-schedules.md](dates-and-schedules.md) first, because 2.x and 3.x give
  different answers for the same schedule string.

## 4. Task callables and transforms
Test the business rules on small, hand-written data where you know the answer, one case per branch of
the rule plus its boundary (on the day, one day either side, missing value).

- Plain functions in a DAG file or a helper module: import them. The conftest puts `dags/` on `sys.path`,
  so `from invoices_daily import overdue_invoices` works (importing the file also defines its DAGs; that is fine).
- Module-level `@task` functions: call the undecorated function through `.function`. Calling the task
  itself outside a running DAG returns an XComArg, not data (verified on 3.3 and 2.11):
  ```python
  from invoices_daily import dedupe_invoices
  assert dedupe_invoices.function(rows) == expected     # dedupe_invoices(rows) -> PlainXComArg
  ```
- TaskFlow tasks defined inside a `@dag` function are not importable. Take the undecorated function from
  the parsed DAG:
  ```python
  fn = dagbag.dags["invoices_daily"].get_task("transform").python_callable
  assert fn(rows, "2026-03-03") == expected
  ```
  Pass context values (`ds`, `logical_date`, ...) explicitly as keyword arguments. A callable that calls
  `get_current_context()` cannot run outside a task; cover it through `dag.test()` (section 6).
- Callables that read files: write the input into `tmp_path`, pass that path (or monkeypatch the module
  constant that holds it), then assert on the rows written, not only on the return value.

## 5. Custom hooks and operators with connections and variables
Supply connections and variables through environment variables. The environment secrets backend is
checked before the metadata DB on both versions, so no DB, no `airflow connections add`, and no session
is needed. Verified on 3.3 and 2.11 for hooks called directly and from `operator.execute()`.
```python
import json


def test_loads_only_the_requested_day(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    # a conn id that is NOT the operator's default, so an operator that ignores conn_id fails
    monkeypatch.setenv("AIRFLOW_CONN_TEST_DB", json.dumps(
        {"conn_type": "generic", "host": str(db_file), "schema": "raw", "extra": {"k": "v"}}))
    monkeypatch.setenv("AIRFLOW_VAR_BATCH_SIZE", "500")      # Variable.get("batch_size") -> "500"

    from company_ops.operators import LoadDayOperator
    op = LoadDayOperator(task_id="t", conn_id="test_db", day="2026-03-03", source=...)
    loaded = op.execute(context={})

    rows = read_rows(db_file, "raw.invoices")      # open the real file the connection points to
    assert loaded == len(rows) == 3
    assert {r["order_date"] for r in rows} == {"2026-03-03"}
```
- Env names: `AIRFLOW_CONN_<CONN_ID upper>`, `AIRFLOW_VAR_<KEY upper>`. The value is JSON (keys
  `conn_type, host, schema, login, password, port, extra`) or a URI (`generic://user:pw@host:5432/schema?k=v`;
  in a URI the path is the schema and extras arrive as strings, so `x:///tmp/f.db` gives host `""` and
  schema `tmp/f.db`: use JSON for file paths). Any `conn_type` works, and a new value for the same id is
  seen on the next lookup (no caching). An unknown conn id raises
  `AirflowNotFoundException` ("isn't defined") on both versions; on 2.x without a migrated DB the
  log also shows an `OperationalError: no such table: connection` from the metadata-DB backend.
- `operator.execute(context={})` runs the real code. On 3.x it logs "cannot be called outside of the Task
  Runner"; the call still works. It does not render Jinja templates: pass concrete values, not
  `"{{ ds }}"`.
- Assert on the side effect in the real target (the file or table the connection points to), not only
  on the return value. A hook that silently falls back to an in-memory database, or an operator that
  drops its filter but still returns the right count, only fails a test that reads the target.
- Rules about re-runs: seed rows for neighbouring dates, run the same day twice, then assert that
  day has no duplicates and the neighbours are untouched.
- Patching `BaseHook.get_connection` is the fallback when env vars cannot express the connection. If you
  patch it, assert it was called with the conn id under test; a patch that returns the same connection
  for any id hides an operator that ignores `conn_id`.
- Deferrable operators: `pytest.raises(TaskDeferred)` around `execute`, then assert on the trigger.

## 6. End-to-end runs with dag.test()
```python
import json
from datetime import datetime, timezone

import airflow


def test_invoices_daily_end_to_end(dagbag, airflow_db, monkeypatch, tmp_path):
    monkeypatch.setenv("AIRFLOW_CONN_ANALYTICS_DB", json.dumps({"conn_type": "generic", "host": str(tmp_path / "test.db")}))
    dag = dagbag.dags["invoices_daily"]
    when = datetime(2026, 3, 3, 7, 30, tzinfo=timezone.utc)
    key = "logical_date" if airflow.__version__.startswith("3.") else "execution_date"
    dr = dag.test(**{key: when})
    states = {ti.task_id: ti.state for ti in dr.get_task_instances()}
    assert dr.state == "success", states          # dag.test() does not raise when a task fails
    rows = read_output(tmp_path, "2026-03-03")      # then check what the run produced:
    assert rows and all(is_overdue(r, "2026-03-03") for r in rows)   # properties from the rule
    assert "INV-7" in {r["id"] for r in rows}       # a row you verified by hand
```
- `dag.test()` returns the DagRun with state `failed` when a task raises; it never raises itself. Without
  the state assertion the test passes on a broken DAG.
- It runs tasks in the pytest process, so `monkeypatch.setenv` connections and variables are visible and
  relative paths resolve against pytest's working directory (the repo root in CI).
- Which day a run processes depends on the version and the timetable; see
  [dates-and-schedules.md](dates-and-schedules.md) section 7 before choosing the date to pass.
- Sensors that wait on external systems: `dag.test(..., mark_success_pattern="wait_for_.*")` marks matching
  tasks successful without running them.
- Airflow 2.x: a second `dag.test()` for the same DAG and date in the same DB fails with
  `NoReferencedTableError ... 'ab_user'`. The conftest's throwaway DB avoids it across pytest runs;
  within one session use one date per DAG, or `import airflow.providers.fab.auth_manager.models` first.
- If a DAG writes into the repo (for example `output/`), redirect it to `tmp_path`. DagBag loads each
  DAG file as a private module, so patch the globals the task function sees, not an imported copy:
  `task_global(dag, "write_summary", "OUTPUT_DIR", tmp_path)` (the conftest fixture; it does
  `monkeypatch.setitem(dag.get_task(...).python_callable.__globals__, ...)`; verified on 3.3 and 2.11
  with `dag.test()`). Patch every task that reads the name: each task's callable shares its file's
  globals, but a helper module imported by the DAG has its own. Otherwise read the output the run
  produced and delete it in teardown. Do not change the DAG to make it testable unless the user agrees.

### Several runs: state carried between runs
A DAG that keeps a watermark, a cursor, running totals or an append-only table is only tested by a
sequence of runs against the same metadata DB and the same output location. One run passes even when
the watermark never advances or a re-run loads the same rows twice.
```python
from datetime import timedelta


def test_three_days_then_rerun(dagbag, airflow_db, task_global, tmp_path):
    dag = dagbag.dags["invoices_daily"]
    task_global(dag, "load", "OUTPUT_DIR", tmp_path)
    key = "logical_date" if airflow.__version__.startswith("3.") else "execution_date"
    first = datetime(2026, 3, 2, 7, 30, tzinfo=timezone.utc)
    for when in [first + timedelta(days=i) for i in range(3)] + [first + timedelta(days=1)]:  # re-run day 2
        dr = dag.test(**{key: when})
        assert dr.state == "success", {ti.task_id: ti.state for ti in dr.get_task_instances()}
    rows = read_output(tmp_path)
    assert len(rows) == len({r["id"] for r in rows})        # nothing loaded twice
    assert {r["day"] for r in rows} == {"2026-03-02", "2026-03-03", "2026-03-04"}
```
- Verified on 3.3 and 2.11, including the re-run of an already-run date. On 2.x that re-run needs
  `import airflow.providers.fab.auth_manager.models` first (in the test or conftest), or it fails with
  the `ab_user` error above.
- `scripts/replay_runs.py` replays a sequence of runs from the command line in one throwaway DB, for a
  quick check before writing the test (`python <skill-dir>/scripts/replay_runs.py DAG_ID --runs 3
  --rerun 2`; see `--help`). Its tasks write wherever the DAG writes, so delete those outputs after.
- `ti.xcom_pull(..., include_prior_dates=True)` reads earlier runs only when they are in the same DB,
  which is another reason to keep every run of the sequence in one session.
- CLI alternative when a separate process is needed: `airflow dags test <dag_id> <date>` exits 0 on
  success and 1 when a task fails (verified on 3.3).
