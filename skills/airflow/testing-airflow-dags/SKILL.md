---
name: testing-airflow-dags
description: >-
  Writes and repairs pytest suites for Apache Airflow projects (2.x or 3.x) that
  must run in CI with no scheduler, webserver or real connections. Use for any
  request to add, fix or strengthen tests of DAG files or of custom Airflow
  operators, hooks, sensors or task functions (a dags/ folder is a strong hint),
  even when the user never says "Airflow": "add a pytest suite for our dags", "make CI fail
  when a DAG doesn't import", "test that every task has 2 retries and the
  schedule is weekdays only", "add unit tests for our custom hook and operator,
  CI has no connections configured", "run the DAG end to end on the sample data
  in a test", "re-runs must not load twice", "our DagBag test broke
  after the upgrade". Also use when existing
  DAG tests pass but would not catch real bugs. Not for writing or fixing the
  DAG code itself (use authoring-airflow-dags), for upgrading DAGs from Airflow 2
  to 3 (use migrating-to-airflow-3), for dbt model or schema tests (use
  testing-dbt-models), or for Snowflake/Databricks query tuning.
license: MIT
compatibility: >-
  Needs the project's Python environment with apache-airflow (2.x or 3.x) and
  pytest installed. Scripts are Python 3 standard library only and run inside
  that environment. No running Airflow services are required.
metadata:
  author: altimate-ai
  version: "0.1.0"
---

# Testing Airflow DAGs

A DAG test suite is worth something only if it fails when the code is wrong. "Green on the current
code" is half of the job; the other half is showing that each test turns red when the rule it
protects is broken. This skill works offline, against plain Airflow, with no deployment.
`<skill-dir>` below is the directory this SKILL.md lives in; run its scripts with the project's
Python (the one that has Airflow and pytest).

## Step 0: find the Airflow version and the rules to test

1. **Version.** Check, in order: `requirements*.txt` / `pyproject.toml` / lockfile pins, then
   `python -c "import airflow; print(airflow.__version__)"` in the project's environment (the one CI
   runs). The major version changes the test APIs (DagBag import and arguments, `dag.test()` keyword,
   hook base classes) and what a schedule string means. Tests written for the wrong major version
   die at collection. If the pin and the installed version disagree, ask which one CI uses.
2. **Facts about the DAGs.** Run the bundled checker once:
   `python <skill-dir>/scripts/airflow_check.py dags/` (add `--json` for machine-readable output). It lists
   every DAG id, file, schedule, timetable, catchup, task count, the next scheduled runs, and any file
   that fails to import. Exit 0 clean, 1 import errors, 2 static errors, 3 usage/env problem. If the
   current code already has import errors and the user asked you not to change the DAGs, report that
   before writing tests.
3. **Rules.** Write down, as a list, the rules the user stated plus any the repo states (README,
   CONTRIBUTING, existing tests). Each rule becomes at least one test. Do not add policies nobody
   asked for ("every DAG must have tags", "catchup must be off"): an invented policy either fails on
   the correct code or locks in an accident the team never agreed to.

## Workflow (copy this checklist and tick it off)

```
- [ ] 0. Version detected; airflow_check.py run; rule list written (from user + repo only)
- [ ] 1. conftest.py written (template below); unit tests of the task callables drafted, run, green
- [ ] 2. Structure/schedule tests + ONE end-to-end test per DAG (multi-run if the DAG keeps state
         across runs); repo outputs redirected with the task_global fixture, never via `import my_dag`
- [ ] 3. pytest tests/ -q --tb=short -> fix the TESTS, re-run, repeat until green (never edit the DAGs)
- [ ] 4. Mutation check: one planted bug per rule with scripts/mutation_check.py; every one caught
- [ ] 5. Survivors: strengthen the test, re-run step 3 AND step 4 until clean
- [ ] 6. git status / git diff: DAG and source files identical to how you found them
- [ ] 7. Final report (template at the end)
```

Budget your turns: draft each test file completely before its first run instead of growing it one
test per run. Several small files (callables, structure, schedule, end to end) beat one large file
that dies at collection and hides every result. Get the cheap unit tests green before writing the
`dag.test()` tests, which take seconds per run and fail for environment reasons. Use the verified
patterns in `references/test-patterns.md` rather than probing Airflow internals by trial and error
(guessed APIs such as timetable iterators that do not exist in the installed version are the usual
time sink). Keep output small: `pytest tests/ -q --tb=short 2>&1 | tail -40`.
**Stop rule:** if an end-to-end test fails twice for an environment reason (paths, DB, imports, a
global you cannot reach), stop debugging the harness: assert on the file the run actually produced,
delete it in teardown, and say so in the report.

**Expected values.** Work out each expected value from the stated rule on a tiny hand-built input.
When a test then disagrees with the current code on a detail the user's wording does not pin down
(an off-by-one in a day count, inclusive vs exclusive bounds, sort order), the current code defines
the behaviour: adjust the expectation and mention the detail in the report. Only when the code
clearly contradicts an explicit rule is it a bug, and then you tell the user; you still do not edit
the DAG. Run `git status` before you start: the user may have uncommitted edits. If you changed a
DAG file by accident, undo only your own change (`git checkout -- <file>` is safe only for a file
that was clean at the start) and re-run.

**Verify until clean.** After every fix, re-run the full `pytest tests/ -q`, not only the test you
touched. A fix often unmasks the next failure (a second import error, a fixture that now reaches a
different branch). Stop only when a full run is green and the mutation check reports zero survivors.

## Setup: conftest.py (both versions)

```python
# tests/conftest.py
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DAGS = REPO / "dags"

# Airflow reads its config once, on first import, so set everything before any airflow import.
_TMP = Path(tempfile.mkdtemp(prefix="dag-tests-"))
os.environ["AIRFLOW__CORE__DAGS_FOLDER"] = str(DAGS)   # 3.x dag.test() requires the DAG to live here
os.environ["AIRFLOW__CORE__LOAD_EXAMPLES"] = "False"
os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = f"sqlite:///{_TMP / 'airflow.db'}"  # throwaway DB
os.environ.setdefault("AIRFLOW_HOME", str(_TMP))
sys.path.insert(0, str(DAGS))  # lets tests import DAG modules and helper packages in dags/


@pytest.fixture(scope="session")
def dagbag():
    try:
        from airflow.dag_processing.dagbag import DagBag  # Airflow >= 3.2
    except ImportError:
        from airflow.models.dagbag import DagBag          # Airflow 2.x, 3.0, 3.1
    return DagBag(dag_folder=str(DAGS))


@pytest.fixture(scope="session")
def airflow_db():
    """Migrates the throwaway metadata DB. Only dag.test() tests need it (about 1 s)."""
    subprocess.run([sys.executable, "-m", "airflow", "db", "migrate"], check=True, capture_output=True)


@pytest.fixture(scope="session")
def upcoming_runs():
    """upcoming_runs(dag, after, n) -> the next n times the scheduler would start a run (aware datetimes)."""
    from airflow.timetables.base import TimeRestriction

    def _runs(dag, after, n):
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

    return _runs


@pytest.fixture
def task_global(monkeypatch):
    """task_global(dag, task_id, NAME, value): patch a module global that the task's code reads."""
    def _set(dag, task_id, name, value):
        g = dag.get_task(task_id).python_callable.__globals__  # the DagBag-loaded module's globals
        assert name in g, f"{task_id} does not read a global named {name}"
        monkeypatch.setitem(g, name, value)
    return _set
```

Schedule test with it (days, time and offset all asserted; a cron-string comparison would miss
`1-5` vs `mon-fri` equivalence and say nothing about the timezone):
```python
def test_weekdays_0730_utc(dagbag, upcoming_runs):
    runs = upcoming_runs(dagbag.dags["my_dag"], datetime(2026, 3, 2, tzinfo=timezone.utc), 10)
    assert len(runs) == 10 and {r.weekday() for r in runs} == {0, 1, 2, 3, 4}
    assert all((r.hour, r.minute, r.utcoffset().total_seconds()) == (7, 30, 0) for r in runs)
```

Why this shape:
- `DagBag(include_examples=False)` raises `TypeError` on Airflow 3.3; the env var does the job on
  every version.
- A throwaway sqlite DB per pytest session keeps tests from writing runs into a developer's metadata DB
  and keeps re-runs independent (on 2.x, re-running `dag.test()` for a date that already has a run in
  the DB crashes with `NoReferencedTableError ... ab_user`).
- `task_global` exists because DagBag imports each DAG file as its own private module
  (`unusual_prefix_...`). `import my_dag; monkeypatch.setattr(my_dag, "OUTPUT_DIR", tmp_path)` patches
  a *different* copy, so `dag.test()` still writes into the repo. Patch through the task's callable
  instead: `task_global(dag, "write_report", "OUTPUT_DIR", tmp_path)` (verified on 3.3 and 2.11).
- Parse the DAGs inside a fixture and look DAGs up inside tests. A module-level `dag = bag.dags["x"]`
  turns a broken DAG into a collection error for the whole file instead of one clear failing test.

## Choosing the test for each kind of rule

| Rule the user states | Test that catches a violation | Weak version that misses it |
|---|---|---|
| "every file must import" | `dagbag.import_errors == {}` plus the set of expected DAG ids is present | import errors only: a DAG that silently stops being defined passes |
| task order / "B only after A" | exact `upstream_task_ids` per task, or `get_flat_relative_ids(upstream=True)` for "after" | checking one edge exists; checking the reverse direction |
| per-task settings (retries, owner, pool) | loop over every task of every DAG, read `task.retries` etc. | reading `dag.default_args`: misses a task-level override |
| schedule ("07:30 UTC, weekdays") | generate the next runs with the timetable and assert day set, time and offset | comparing cron strings; checking only the time |
| catchup / max_active_runs | assert the attribute on the named DAG(s) | none, if the user asked for it |
| business logic in a task | call the function with small hand-built rows, one case per branch and boundary | only the happy path; asserting the row count but not which rows |
| custom operator / hook | real `execute()` against a temp file or DB, connection from `AIRFLOW_CONN_*`, assert on the target's contents | mocking the target away; asserting only the return value |
| state carried between runs (watermark, cursor, running totals, "loaded exactly once", re-runs) | several consecutive runs in ONE metadata DB and one output location, then a re-run of an earlier date; assert the final state and that nothing doubled or went missing | one run, which cannot see a watermark that never advances or a re-run that loads twice |
| "runs end to end on the sample data" | `dag.test()` + assert `dr.state == "success"` + the output exists for the right date + properties checkable by rule (every output row satisfies the rule, a few rows you verified by hand are present or absent) | not checking the state (`dag.test()` does not raise on task failure); hand-computing the entire output of a real sample file, which costs many turns and is easy to get wrong. Exact expectations belong in the unit tests where you control the input |

Verified code for every row is in `references/test-patterns.md`.

## Mutation check: prove the suite catches bugs

For each rule, plant the smallest realistic bug that breaks it, run the suite, and put the code back.
The bundled script does this safely (restores bytes and mtime even on failure, checks the hash):

```bash
python <skill-dir>/scripts/mutation_check.py \
  --mutation dags/billing.py '"retries": 2' '"retries": 0' \
  --mutation dags/billing.py 'download >> parse >> store' 'download >> store' \
  --mutation dags/billing.py 'if amount < 0:' 'if amount < -1:' \
  -- tests/
```
- `OLD` must occur exactly once in the file (include surrounding text to make it unique).
- It first runs the suite unmodified; if that is not green it stops with exit 1.
- JSON on stdout: per mutation `caught`, the tests that caught it, and `collection_only` (caught only
  because a test module failed to import; restructure so a named test fails). Exit 0 all caught,
  2 some survived, 3 usage error.
- Mutate behaviour the rule is about (a filter, a comparison, an edge, a schedule field, a conn id),
  not formatting. Also plant one bug in each custom operator/hook the user named.
- A survivor means the test is too weak. Strengthen it, then re-run pytest and the whole mutation list.

Doing it by hand is fine when the script cannot express the bug (for example deleting a file): copy
the file aside first, edit, run, restore the copy, and confirm `git diff` is what it was before.
Exit 2 also covers `inconclusive_ids`: runs that timed out or crashed pytest without a failing test
prove nothing; make the mutation smaller or fix the suite.

## Gotchas

- **`bag.get_dag(dag_id)` queries the metadata DB** on both 2.x and 3.x ("no such table: dag" without a
  migrated DB). Use `bag.dags[dag_id]`.
- **3.x `dag.test()`** needs a migrated DB and the DAG file inside `AIRFLOW__CORE__DAGS_FOLDER`;
  otherwise "Cannot create DagRun ... dag is not serialized". The keyword is `logical_date=` on 3.x and
  `execution_date=` on 2.x.
- **`dag.test()` returns a failed DagRun instead of raising.** Always assert `dr.state == "success"` and
  include the per-task states in the assertion message.
- **Connections and variables in tests come from env vars**, set per test with `monkeypatch.setenv`.
  Use the JSON form: `monkeypatch.setenv("AIRFLOW_CONN_TEST_DB", json.dumps({"conn_type": "generic",
  "host": str(tmp_path / "test.db"), "schema": "raw", "extra": {...}}))`, and
  `AIRFLOW_VAR_<KEY>` for variables. This works outside a task on both versions, with no DB, any
  `conn_type`, and a new value for the same id is picked up on the next lookup. Avoid URIs for file
  paths: `scheme:///tmp/f.db` parses as host `""` and schema `tmp/f.db`. Do not
  seed connections with `airflow connections add`, `Session`/`create_session`, or private helpers
  such as `airflow.sdk.execution_time` `_preset_*` functions: CI has no such state, the private APIs
  change between releases, and those tests break on the correct code.
- **Use a conn id that is not the code's default** (for example `test_db` when the default is
  `analytics_db`), and make sure the default is not also defined. Otherwise an operator that ignores the
  `conn_id` it was given still passes.
- **`operator.execute(context={})` skips Jinja rendering.** Pass concrete values for templated fields.
  On 3.x it logs "cannot be called outside of the Task Runner" and still runs.
- **Never snapshot the code** (hashing DAG files, comparing source text or AST). Such tests fail on a
  harmless comment and prove nothing about behaviour.
- **A schedule string means different run dates on 2.x and 3.x** (3.x cron strings fire *at* the tick
  with a zero-width interval; 2.x runs cover the previous period). Read
  `references/dates-and-schedules.md` before asserting which day a run processes.
- **Multi-run tests:** loop `dag.test()` over consecutive dates inside one test (one DB, one
  `tmp_path`, distinct dates), or replay the runs with `scripts/replay_runs.py`. Watermarks and
  `xcom_pull(..., include_prior_dates=True)` only show their bugs on the second or third run.
- **Calling a `@task` function in a test does not run it.** Outside a running DAG, `my_task(rows)`
  returns an XComArg, not data (`assert <PlainXComArg> == ...`, "XComArg only supports ..."). For a
  module-level `@task`, call the undecorated function: `my_dag.my_task.function(rows)`. For one
  defined inside `@dag`, use `dag.get_task("id").python_callable`. Pass context values as keywords.
- **Leave the DAGs alone** unless the user asks. If a stated rule fails on the current code, the test
  is right and the code is wrong: tell the user instead of weakening the test or editing the DAG.
- Inherited config: an `AIRFLOW_HOME` or `airflow.cfg` from another Airflow version can break the
  import (for example "could not be loaded ... xcom_backend"). The conftest's temp home avoids it when
  `AIRFLOW_HOME` is unset; otherwise point it at a fresh directory.

## References (read only when needed)

- `references/test-patterns.md`: read before writing structure, schedule, callable, operator/hook or
  `dag.test()` tests. It has the 2.x/3.x API table and verified code for each.
- `references/dates-and-schedules.md`: read only when a test asserts which date or data interval a run
  processes, catchup behaviour, or what a manual or backfill run sees.
- `scripts/airflow_check.py --help`: import errors, DAG facts, next-run previews and version-aware static
  findings (context keys removed in 3.x, top-level I/O, and more). Use its `next_runs` as a
  cross-check for schedule tests.
- `scripts/mutation_check.py --help`: planted-bug runner described above.
- `scripts/replay_runs.py --help`: replays several runs of a DAG in one throwaway DB; use it to see
  what a run sequence does before writing the multi-run test.

## Final report

End with a short report, and be exact about what ran:

```
Airflow version: <x.y> (from <where>)
Tests: <file list>; pytest tests/ -q -> <N passed> in <env>
Rules covered: <rule> -> <test name>  (one line each; say which user rules have no test and why)
Mutation check: <k>/<n> caught; survivors: <none | list and why acceptable>
Not verified: <e.g. real connections, scheduler behaviour, other Airflow versions>
DAG code changed: no (git diff dags/ empty)
```
