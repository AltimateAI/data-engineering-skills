"""Shared helpers for Airflow eval graders (``evals/airflow/cases/*/grade.py``).

Graders run under the case's Airflow env interpreter, e.g.::

    ~/.cache/des-evals/airflow-3.3/bin/python grade.py \
        --workspace DIR --events EVENTS.jsonl --out RESULT.json

and import this module through ``EVAL_HARNESS_DIR``::

    import os, sys
    sys.path.insert(0, os.environ["EVAL_HARNESS_DIR"])
    import grading as g

Design rules:
- Never trust agent claims: every helper executes code in a subprocess.
- Every Airflow invocation gets its own ``AIRFLOW_HOME`` (sqlite, no examples,
  ``dags_folder = <workspace>/dags``) and a scrubbed ``AIRFLOW__*`` environment.
- Only the standard library is used, so the module also imports under the
  harness interpreter (``run_eval.py``, ``report.py``, unit tests).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# --------------------------------------------------------------------------
# Environments
# --------------------------------------------------------------------------

#: case.yaml ``airflow_version`` -> venv directory name under EVAL_ENV_ROOT.
ENV_DIRS = {"3.3": "airflow-3.3", "2.11": "airflow-2.11"}
#: case.yaml ``airflow_version`` -> venv the *agent* uses. Separate from the grader
#: envs so an agent that installs or edits packages can never change grading.
AGENT_ENV_DIRS = {"3.3": "agent-airflow-3.3", "2.11": "agent-airflow-2.11"}
DEFAULT_TIMEOUT_S = 300
_RESULT_MARKER = "__EVAL_PROBE_RESULT__"
# Environment variables never inherited by Airflow subprocesses.
_SCRUB_PREFIXES = ("AIRFLOW__", "AIRFLOW_CONN_", "AIRFLOW_VAR_")
_SCRUB_EXACT = ("AIRFLOW_HOME", "AIRFLOW_CONFIG", "VIRTUAL_ENV", "PYTHONHOME")


def env_root() -> Path:
    """Root holding the Airflow venvs (``$EVAL_ENV_ROOT`` or ``~/.cache/des-evals``)."""
    return Path(os.environ.get("EVAL_ENV_ROOT", "~/.cache/des-evals")).expanduser()


def env_python(airflow_version: str) -> str:
    """Interpreter of the venv for a case ``airflow_version`` ("3.3" or "2.11")."""
    try:
        name = ENV_DIRS[str(airflow_version)]
    except KeyError as exc:
        raise ValueError(
            f"unsupported airflow_version {airflow_version!r}; expected one of {sorted(ENV_DIRS)}"
        ) from exc
    return str(env_root() / name / "bin" / "python")


def agent_env_python(airflow_version: str) -> str:
    """Interpreter of the agent's own venv for a case ``airflow_version``."""
    try:
        name = AGENT_ENV_DIRS[str(airflow_version)]
    except KeyError as exc:
        raise ValueError(
            f"unsupported airflow_version {airflow_version!r}; expected one of {sorted(AGENT_ENV_DIRS)}"
        ) from exc
    return str(env_root() / name / "bin" / "python")


def _resolve_py(env_py: str | None) -> str:
    return env_py or sys.executable


def _bin(env_py: str | None, name: str) -> str:
    return str(Path(_resolve_py(env_py)).parent / name)


def scrubbed_environ(base: dict[str, str] | None = None) -> dict[str, str]:
    """Copy of ``base`` (default ``os.environ``) without inherited Airflow config."""
    src = dict(os.environ if base is None else base)
    return {
        k: v
        for k, v in src.items()
        if not k.startswith(_SCRUB_PREFIXES) and k not in _SCRUB_EXACT
    }


def airflow_env(
    workspace: str | os.PathLike,
    extra: dict[str, str] | None = None,
    airflow_home: str | os.PathLike | None = None,
    env_py: str | None = None,
) -> dict[str, str]:
    """Environment for running Airflow against ``workspace`` in a fresh AIRFLOW_HOME.

    - ``AIRFLOW_HOME``: a new temp dir (or ``airflow_home``) with its own sqlite DB.
    - ``AIRFLOW__CORE__DAGS_FOLDER=<workspace>/dags``, examples off, unit-test mode off.
    - Inherited ``AIRFLOW__*`` / ``AIRFLOW_CONN_*`` / ``AIRFLOW_VAR_*`` are removed;
      pass them back explicitly through ``extra`` when a case needs them.
    - macOS fork-safety workarounds (``OBJC_DISABLE_INITIALIZE_FORK_SAFETY``, ``no_proxy``).
    - ``PATH`` starts with the env's ``bin`` so ``airflow``/``pytest``/``ruff`` resolve there.
    - ``PYTHONPATH`` includes the workspace root so ``dags/`` can import project packages.

    The DB is created lazily by :func:`ensure_db` (``run_dags_test`` calls it).
    """
    ws = Path(workspace).resolve()
    home = Path(airflow_home) if airflow_home else Path(tempfile.mkdtemp(prefix="eval-af-home-"))
    home.mkdir(parents=True, exist_ok=True)
    env = scrubbed_environ()
    bin_dir = str(Path(_resolve_py(env_py)).parent)
    env.update(
        {
            "AIRFLOW_HOME": str(home),
            "AIRFLOW__CORE__DAGS_FOLDER": str(ws / "dags"),
            "AIRFLOW__CORE__LOAD_EXAMPLES": "False",
            "AIRFLOW__CORE__UNIT_TEST_MODE": "False",
            "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN": f"sqlite:///{home / 'airflow.db'}",
            "AIRFLOW__LOGGING__LOGGING_LEVEL": "INFO",
            "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
            "no_proxy": "*",
            "NO_PROXY": "*",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join(
                p for p in (str(ws), env.get("PYTHONPATH", "")) if p
            ),
            "PATH": os.pathsep.join((bin_dir, env.get("PATH", ""))),
        }
    )
    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return env


@dataclass
class ProcResult:
    """Outcome of a subprocess run by a helper."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    cmd: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def output(self) -> str:
        return self.stdout + ("\n" if self.stdout and self.stderr else "") + self.stderr

    def tail(self, n: int = 40) -> str:
        return "\n".join(self.output.strip().splitlines()[-n:])


def run_cmd(
    cmd: Sequence[str],
    env: dict[str, str] | None = None,
    cwd: str | os.PathLike | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    input_text: str | None = None,
) -> ProcResult:
    """Run ``cmd`` in its own process group; kill the whole group on timeout."""
    proc = subprocess.Popen(
        list(cmd),
        env=env,
        cwd=str(cwd) if cwd else None,
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(input=input_text, timeout=timeout)
        return ProcResult(proc.returncode, out, err, False, list(cmd))
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        out, err = proc.communicate()
        return ProcResult(-9, out or "", (err or "") + f"\n[timed out after {timeout}s]", True, list(cmd))


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


def ensure_db(env_py: str | None, env: dict[str, str], timeout: float = DEFAULT_TIMEOUT_S) -> ProcResult:
    """Run ``airflow db migrate`` once per AIRFLOW_HOME (marker file makes it idempotent)."""
    marker = Path(env["AIRFLOW_HOME"]) / ".eval_db_ready"
    if marker.exists():
        return ProcResult(0, "db already migrated", "")
    res = run_cmd([_bin(env_py, "airflow"), "db", "migrate"], env=env, timeout=timeout)
    if res.ok:
        marker.write_text("ok")
    return res


# --------------------------------------------------------------------------
# Python probes
# --------------------------------------------------------------------------


def run_python_in_env(
    env_py: str | None,
    code: str,
    workspace: str | os.PathLike,
    env: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> ProcResult:
    """Run ``code`` with the env interpreter, cwd=workspace, fresh Airflow env by default."""
    env = env if env is not None else airflow_env(workspace, env_py=env_py)
    return run_cmd([_resolve_py(env_py), "-c", code], env=env, cwd=workspace, timeout=timeout)


#: Helpers defined in every :func:`probe_json` snippet. ``get_dag`` reads the
#: parsed DagBag directly: ``DagBag.get_dag`` queries the metadata DB, which a
#: fresh probe environment does not have.
PROBE_PRELUDE = '''
def dagbag(folder=None):
    import os, airflow
    folder = folder or os.environ["AIRFLOW__CORE__DAGS_FOLDER"]
    if int(airflow.__version__.split(".")[0]) >= 3:
        from airflow.dag_processing.dagbag import DagBag
        return DagBag(dag_folder=folder)
    from airflow.models import DagBag
    return DagBag(dag_folder=folder, include_examples=False)

def get_dag(dag_id, folder=None):
    bag = dagbag(folder)
    if dag_id not in bag.dags:
        raise KeyError(f"DAG {dag_id!r} not found; import errors: {bag.import_errors}")
    return bag.dags[dag_id]

def core_timetable(dag):
    """Scheduler-side timetable (3.x SDK timetables lack next_dagrun_info)."""
    try:
        from airflow.serialization.serialized_objects import coerce_to_core_timetable
    except ImportError:
        return dag.timetable
    return coerce_to_core_timetable(dag.timetable)

def scheduled_intervals(dag, earliest, n=3, catchup=True, latest=None):
    """First ``n`` scheduled runs from ``earliest`` as ISO dicts
    ``{"start", "end", "run_after"}`` (data interval + when the run is created)."""
    import pendulum
    from airflow.timetables.base import TimeRestriction
    tt = core_timetable(dag)
    if isinstance(earliest, str):
        earliest = pendulum.parse(earliest)
    out, last = [], None
    for _ in range(n):
        info = tt.next_dagrun_info(last_automated_data_interval=last,
                                   restriction=TimeRestriction(earliest=earliest, latest=latest, catchup=catchup))
        if info is None:
            break
        last = info.data_interval
        out.append({"start": info.data_interval.start.isoformat(), "end": info.data_interval.end.isoformat(),
                    "run_after": info.run_after.isoformat()})
    return out

def manual_interval(dag, run_after):
    """Data interval a manual run triggered at ``run_after`` would get."""
    import pendulum
    if isinstance(run_after, str):
        run_after = pendulum.parse(run_after)
    di = core_timetable(dag).infer_manual_data_interval(run_after=run_after)
    return {"start": di.start.isoformat(), "end": di.end.isoformat()}
'''


def probe_json(
    env_py: str | None,
    code: str,
    workspace: str | os.PathLike,
    env: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> tuple[Any, ProcResult]:
    """Run ``code`` that assigns a JSON-serialisable ``RESULT``; return ``(RESULT, proc)``.

    ``code`` may be indented (it is dedented). :data:`PROBE_PRELUDE` provides
    version-agnostic helpers: ``dagbag()``, ``get_dag(dag_id)``,
    ``core_timetable(dag)``, ``scheduled_intervals(dag, earliest, n, catchup)``
    and ``manual_interval(dag, run_after)``. ``RESULT`` is ``None`` when the
    probe crashed or never assigned it; inspect ``proc.tail()`` for the reason.
    Example (schedule assertions)::

        res, proc = g.probe_json(py, '''
            dag = get_dag("daily_sales")
            RESULT = {"runs": scheduled_intervals(dag, "2026-01-01T00:00:00+00:00", n=2),
                      "manual": manual_interval(dag, "2026-03-01T05:00:00+00:00")}
        ''', workspace)
        # 3.3 cron string -> CronTriggerTimetable: start == end == run_after
    """
    import textwrap

    wrapped = (
        "import json as __j\nRESULT = None\n"
        + PROBE_PRELUDE
        + textwrap.dedent(code).strip("\n")
        + f"\nprint({_RESULT_MARKER!r} + __j.dumps(RESULT, default=str))\n"
    )
    proc = run_python_in_env(env_py, wrapped, workspace, env=env, timeout=timeout)
    return parse_probe_output(proc.stdout), proc


def parse_probe_output(stdout: str) -> Any:
    """Extract the last ``RESULT`` emitted by :func:`probe_json` from stdout."""
    for line in reversed(stdout.splitlines()):
        if line.startswith(_RESULT_MARKER):
            try:
                return json.loads(line[len(_RESULT_MARKER):])
            except ValueError:
                return None
    return None


_IMPORT_PROBE = r'''
import json, os, sys, warnings
import airflow
AF = airflow.__version__
MAJOR = int(AF.split(".")[0])
if MAJOR >= 3:
    from airflow.dag_processing.dagbag import DagBag
    make_bag = lambda folder: DagBag(dag_folder=folder)
else:
    from airflow.models import DagBag
    make_bag = lambda folder: DagBag(dag_folder=folder, include_examples=False)

folder = os.environ["AIRFLOW__CORE__DAGS_FOLDER"]
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    bag = make_bag(folder)

def iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else (None if v is None else str(v))

def rel(p):
    try:
        return os.path.relpath(p, os.getcwd())
    except ValueError:
        return p

dags = {}
for dag_id, dag in bag.dags.items():
    tt = getattr(dag, "timetable", None)
    sched = getattr(dag, "schedule", None) if MAJOR >= 3 else getattr(dag, "schedule_interval", None)
    tasks = {}
    for t in dag.tasks:
        tasks[t.task_id] = {
            "task_type": getattr(t, "task_type", type(t).__name__),
            "operator_class": type(t).__name__,
            # MappedOperator, TaskFlow's DecoratedMappedOperator, or any task inside an expanded task group
            "mapped": type(t).__name__.endswith("MappedOperator")
                or getattr(t, "get_closest_mapped_task_group", lambda: None)() is not None,
            "retries": getattr(t, "retries", None),
            "trigger_rule": str(getattr(t, "trigger_rule", "")),
            "pool": getattr(t, "pool", None),
            "upstream": sorted(t.upstream_task_ids),
            "downstream": sorted(t.downstream_task_ids),
        }
    dags[dag_id] = {
        "fileloc": rel(dag.fileloc),
        "tasks": sorted(tasks),
        "task_details": tasks,
        "deps": sorted([u, d] for u in tasks for d in tasks[u]["downstream"]),
        "schedule": repr(sched),
        "timetable": type(tt).__name__ if tt is not None else None,
        "timetable_summary": getattr(tt, "summary", None),
        "catchup": getattr(dag, "catchup", None),
        "start_date": iso(getattr(dag, "start_date", None)),
        "end_date": iso(getattr(dag, "end_date", None)),
        "max_active_runs": getattr(dag, "max_active_runs", None),
        "tags": sorted(getattr(dag, "tags", None) or []),
        "params": sorted((getattr(dag, "params", None) or {}).keys()),
        "default_args": sorted((getattr(dag, "default_args", None) or {}).keys()),
    }

warns = [
    {"category": w.category.__name__, "message": str(w.message)[:500],
     "filename": rel(w.filename), "lineno": w.lineno}
    for w in caught
]
# DagBag (2.9+) captures warnings raised while importing each file itself.
import re as _re
for path, lines in (getattr(bag, "captured_warnings", None) or {}).items():
    for line in lines:
        m = _re.match(r"^(.*?):(\d+): (?:[\w.]+\.)?(\w+): (.*)$", line, _re.S)
        if m:
            warns.append({"category": m.group(3), "message": m.group(4)[:500],
                          "filename": rel(m.group(1)), "lineno": int(m.group(2))})
        else:
            warns.append({"category": "Warning", "message": line[:500], "filename": rel(path), "lineno": None})
RESULT = {
    "airflow_version": AF,
    "dags": dags,
    "import_errors": {rel(k): v for k, v in bag.import_errors.items()},
    "warnings": warns,
}
'''


def import_dags(
    env_py: str | None,
    workspace: str | os.PathLike,
    env: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Parse ``<workspace>/dags`` with the version-appropriate DagBag in a subprocess.

    Returns::

        {"airflow_version": "3.3.2",
         "dags": {dag_id: {"fileloc", "tasks": [ids], "task_details": {id: {...}},
                           "deps": [[up, down], ...], "schedule": repr, "timetable": cls,
                           "timetable_summary", "catchup", "start_date", "end_date",
                           "max_active_runs", "tags", "params", "default_args"}},
         "import_errors": {relpath: traceback},
         "warnings": [{"category", "message", "filename", "lineno"}],   # raised while parsing
         "ok": bool,              # probe ran and returned a result
         "probe_error": str|None}  # tail of output when the probe itself crashed

    3.x uses ``airflow.dag_processing.dagbag.DagBag`` (no ``include_examples``);
    2.x uses ``airflow.models.DagBag(include_examples=False)``.
    """
    result, proc = probe_json(env_py, _IMPORT_PROBE, workspace, env=env, timeout=timeout)
    if result is None:
        return {
            "airflow_version": None,
            "dags": {},
            "import_errors": {},
            "warnings": [],
            "ok": False,
            "probe_error": proc.tail(60),
        }
    result["ok"] = True
    result["probe_error"] = None
    return result


def deprecation_warnings(import_result: dict[str, Any], workspace_only: bool = True) -> list[dict]:
    """Deprecation-type warnings from :func:`import_dags`, optionally only those in workspace files."""
    out = []
    for w in import_result.get("warnings", []):
        if "eprecat" not in w.get("category", "") and "RemovedIn" not in w.get("category", ""):
            continue
        fn = w.get("filename") or ""
        if workspace_only and (fn.startswith("..") or os.path.isabs(fn)):
            continue
        out.append(w)
    return out


# --------------------------------------------------------------------------
# Running DAGs
# --------------------------------------------------------------------------

_DAGRUN_PROBE = r'''
import sys
from airflow.models.dagrun import DagRun
from airflow.models.taskinstance import TaskInstance
from airflow.utils.session import create_session
dag_id = sys.argv[1] if len(sys.argv) > 1 else DAG_ID
with create_session() as s:
    runs = s.query(DagRun).filter(DagRun.dag_id == dag_id).all()
    out = []
    for r in runs:
        tis = s.query(TaskInstance).filter(TaskInstance.dag_id == dag_id, TaskInstance.run_id == r.run_id).all()
        out.append({
            "run_id": r.run_id,
            "state": str(r.state.value if hasattr(r.state, "value") else r.state),
            "logical_date": (getattr(r, "logical_date", None) or getattr(r, "execution_date", None)).isoformat()
                if (getattr(r, "logical_date", None) or getattr(r, "execution_date", None)) else None,
            "data_interval_start": r.data_interval_start.isoformat() if r.data_interval_start else None,
            "data_interval_end": r.data_interval_end.isoformat() if r.data_interval_end else None,
            "tasks": {
                (ti.task_id if ti.map_index < 0 else f"{ti.task_id}[{ti.map_index}]"):
                    str(ti.state.value if hasattr(ti.state, "value") else ti.state)
                for ti in tis
            },
        })
RESULT = out
'''


@dataclass
class DagTestResult:
    """Outcome of ``airflow dags test``; ``ok`` needs rc 0 AND a successful DagRun row."""

    ok: bool
    returncode: int
    timed_out: bool
    log: str
    runs: list[dict] = field(default_factory=list)

    def __iter__(self):  # allows ``ok, log = run_dags_test(...)``
        return iter((self.ok, self.log))

    def failed_tasks(self) -> list[str]:
        return [
            tid
            for run in self.runs
            for tid, state in run.get("tasks", {}).items()
            if state in ("failed", "upstream_failed")
        ]


def run_dags_test(
    env_py: str | None,
    workspace: str | os.PathLike,
    dag_id: str,
    logical_date: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    conf: dict | None = None,
) -> DagTestResult:
    """Run ``airflow dags test <dag_id> [logical_date]`` against the workspace.

    Unpacks as ``ok, log = run_dags_test(...)``. The result also carries
    ``runs`` (DagRun + task-instance states read back from the metadata DB).
    ``ok`` requires exit code 0 and every recorded run of ``dag_id`` in state
    ``success``: the exit code alone is not trusted.

    Pass the same ``env`` to execute a second run against the same DB, or a new
    :func:`airflow_env` for a clean DB. ``logical_date`` is an ISO date/datetime.
    """
    env = env if env is not None else airflow_env(workspace, env_py=env_py)
    db = ensure_db(env_py, env, timeout=timeout)
    if not db.ok:
        return DagTestResult(False, db.returncode, db.timed_out, "airflow db migrate failed:\n" + db.tail(60))
    cmd = [_bin(env_py, "airflow"), "dags", "test", dag_id]
    if logical_date:
        cmd.append(logical_date)
    if conf is not None:
        cmd += ["--conf", json.dumps(conf)]
    res = run_cmd(cmd, env=env, cwd=workspace, timeout=timeout)
    runs = dag_runs(env_py, workspace, dag_id, env=env)
    run_ok = bool(runs) and all(r["state"] == "success" and r["tasks"] for r in runs)  # no TIs = nothing ran (e.g. logical_date < start_date)
    ok = res.ok and run_ok
    log = res.output
    if res.ok and not run_ok:
        log += f"\n[grading] exit code 0 but DagRun states were: {[r['state'] for r in runs]}"
    return DagTestResult(ok, res.returncode, res.timed_out, log, runs)


def dag_runs(
    env_py: str | None,
    workspace: str | os.PathLike,
    dag_id: str,
    env: dict[str, str],
) -> list[dict]:
    """DagRuns (with per-task states) recorded for ``dag_id`` in ``env``'s metadata DB."""
    code = f"DAG_ID = {dag_id!r}\n" + _DAGRUN_PROBE
    result, _ = probe_json(env_py, code, workspace, env=env)
    return result or []


# --------------------------------------------------------------------------
# Static checks
# --------------------------------------------------------------------------


def ruff_air(
    env_py: str | None,
    workspace: str | os.PathLike,
    paths: Sequence[str] = ("dags",),
    select: str = "AIR",
    preview: bool = False,
) -> list[dict]:
    """Ruff findings for ``select`` (default all AIR rules) over ``paths``.

    Runs ``ruff check --isolated`` so the workspace's own ruff config cannot
    silence rules. Returns ``[{"code", "filename" (relative), "line", "message"}]``.
    Raises ``RuntimeError`` if ruff itself fails (exit code 2).
    """
    ws = Path(workspace).resolve()
    targets = [p for p in paths if (ws / p).exists()]
    if not targets:
        return []
    cmd = [_bin(env_py, "ruff"), "check", "--isolated", "--no-cache", "--exit-zero",
           "--output-format", "json", "--select", select]
    if preview:
        cmd.append("--preview")
    res = run_cmd(cmd + targets, cwd=ws, env=scrubbed_environ(), timeout=120)
    if res.returncode != 0:
        raise RuntimeError(f"ruff failed: {res.tail(20)}")
    return parse_ruff_json(res.stdout, ws)


def parse_ruff_json(stdout: str, workspace: str | os.PathLike) -> list[dict]:
    """Normalise ``ruff --output-format json`` output."""
    items = json.loads(stdout or "[]")
    ws = str(Path(workspace).resolve())
    out = []
    for it in items:
        fn = it.get("filename", "")
        if fn.startswith(ws):
            fn = os.path.relpath(fn, ws)
        out.append(
            {
                "code": it.get("code"),
                "filename": fn,
                "line": (it.get("location") or {}).get("row"),
                "message": it.get("message", ""),
            }
        )
    return out


def air_select_for(airflow_version: str | None) -> str:
    """Ruff AIR selection appropriate for a target version.

    Airflow 3 projects: every AIR rule. Airflow 2 projects: only the
    version-neutral families (AIR0xx, AIR2xx); AIR3xx are Airflow-3 migration
    rules that flag correct 2.x code.
    """
    if airflow_version and str(airflow_version).split(".")[0] == "2":
        return "AIR0,AIR2"
    return "AIR"


def python_files(workspace: str | os.PathLike, subdir: str = "dags") -> list[Path]:
    """All ``.py`` files under ``workspace/subdir`` (sorted)."""
    root = Path(workspace) / subdir
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts) if root.exists() else []


# --------------------------------------------------------------------------
# pytest
# --------------------------------------------------------------------------

#: exception types that mean "the test could not even load the code under test".
IMPORT_ERROR_TYPES = ("ImportError", "ModuleNotFoundError", "SyntaxError", "IndentationError")


@dataclass
class TestCaseOutcome:
    nodeid: str
    outcome: str  # passed | failed | error | skipped
    phase: str  # call | setup | teardown | collection
    exc_type: str | None = None
    message: str = ""

    @property
    def is_import_problem(self) -> bool:
        return self.phase == "collection" or (self.exc_type or "") in IMPORT_ERROR_TYPES


@dataclass
class PytestResult:
    """Structured pytest outcome.

    ``status`` is one of: ``passed`` (tests ran, none failed), ``failed`` (at
    least one test failed or errored at runtime), ``collection_error`` (a module
    could not be imported/collected), ``no_tests``, ``timeout``, ``error``
    (pytest usage/internal error).
    """

    status: str
    returncode: int
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    tests: list[TestCaseOutcome] = field(default_factory=list)
    collection_errors: list[str] = field(default_factory=list)
    output_tail: str = ""

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped

    @property
    def behavioral_failures(self) -> list[TestCaseOutcome]:
        """Tests that failed/errored for a reason other than import or collection problems."""
        return [t for t in self.tests if t.outcome in ("failed", "error") and not t.is_import_problem]

    @property
    def import_failures(self) -> list[TestCaseOutcome]:
        return [t for t in self.tests if t.outcome in ("failed", "error") and t.is_import_problem]

    @property
    def caught_bug(self) -> bool:
        """True when the suite ran and >=1 test failed for a behavioral reason (planted-bug check)."""
        return not self.collection_errors and bool(self.behavioral_failures)

    def summary(self) -> str:
        s = f"{self.status}: {self.passed} passed, {self.failed} failed, {self.errors} errors, {self.skipped} skipped"
        if self.collection_errors:
            s += f"; collection errors in {self.collection_errors}"
        bf = self.behavioral_failures
        if bf:
            s += "; behavioral failures: " + ", ".join(f"{t.nodeid} [{t.exc_type}]" for t in bf[:5])
        return s

    def to_dict(self) -> dict:
        d = asdict(self)
        d["caught_bug"] = self.caught_bug
        return d


def run_pytest(
    env_py: str | None,
    workspace: str | os.PathLike,
    paths: Sequence[str] = ("tests",),
    env: dict[str, str] | None = None,
    timeout: float = 600,
    extra_args: Sequence[str] = (),
) -> PytestResult:
    """Run pytest (env interpreter, cwd=workspace) and classify the outcome via JUnit XML.

    Uses a fresh :func:`airflow_env` unless ``env`` is given, disables the cache
    provider and writes the JUnit report outside the workspace.
    """
    ws = Path(workspace).resolve()
    env = env if env is not None else airflow_env(ws, env_py=env_py)
    with tempfile.TemporaryDirectory(prefix="eval-pytest-") as td:
        xml_path = Path(td) / "junit.xml"
        cmd = [_resolve_py(env_py), "-m", "pytest", "-p", "no:cacheprovider", "-q",
               "-o", "junit_family=xunit2", f"--junitxml={xml_path}", *extra_args, *paths]
        res = run_cmd(cmd, env=env, cwd=ws, timeout=timeout)
        xml_text = xml_path.read_text() if xml_path.exists() else ""
    return classify_pytest(res.returncode, xml_text, res.output, timed_out=res.timed_out)


def classify_pytest(returncode: int, junit_xml: str, output: str = "", timed_out: bool = False) -> PytestResult:
    """Pure classifier behind :func:`run_pytest` (unit-tested)."""
    tests = parse_junit(junit_xml) if junit_xml else []
    collection = sorted({t.nodeid for t in tests if t.phase == "collection"})
    if not collection:  # fall back to console output when the JUnit report lacks it
        collection = sorted(set(re.findall(r"ERROR collecting (\S+)", output)))
    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for t in tests:
        if t.phase != "collection":
            counts[t.outcome] = counts.get(t.outcome, 0) + 1
    if timed_out:
        status = "timeout"
    elif collection or (returncode == 2 and "error" in output.lower() and "collect" in output.lower()):
        status = "collection_error"
    elif returncode == 5:
        status = "no_tests"
    elif returncode == 0:
        status = "passed"
    elif returncode == 1:
        status = "failed"
    else:
        status = "error"
    return PytestResult(
        status=status,
        returncode=returncode,
        passed=counts["passed"],
        failed=counts["failed"],
        errors=counts["error"],
        skipped=counts["skipped"],
        tests=tests,
        collection_errors=collection,
        output_tail="\n".join(output.strip().splitlines()[-40:]),
    )


_EXC_RE = re.compile(r"^(?:[\w.]+\.)?([A-Z]\w*(?:Error|Exception|Exit|Warning|Failed|Interrupt))\b")
_TRACE_EXC_RE = re.compile(r"^E\s+(?:[\w.]+\.)?([A-Z]\w*(?:Error|Exception|Exit|Warning|Failed))\b", re.M)


def _exc_type(message: str, text: str) -> str | None:
    m = _EXC_RE.match((message or "").strip())
    if m:
        return m.group(1)
    if (message or "").strip().startswith("assert"):
        return "AssertionError"
    found = _TRACE_EXC_RE.findall(text or "")
    if found:
        return found[-1]
    if re.search(r"^E\s+assert\b", text or "", re.M):
        return "AssertionError"
    return None


def parse_junit(junit_xml: str) -> list[TestCaseOutcome]:
    """Parse pytest JUnit XML into :class:`TestCaseOutcome` rows."""
    root = ET.fromstring(junit_xml)
    out: list[TestCaseOutcome] = []
    for tc in root.iter("testcase"):
        cls, name = tc.get("classname", ""), tc.get("name", "")
        nodeid = f"{cls}::{name}" if cls else name
        outcome, phase, exc, msg = "passed", "call", None, ""
        for child in tc:
            tag = child.tag
            if tag not in ("failure", "error", "skipped"):
                continue
            msg = child.get("message", "") or ""
            text = child.text or ""
            if tag == "skipped":
                outcome = "skipped"
                continue
            if tag == "failure":
                outcome, phase = "failed", "call"
            else:
                outcome = "error"
                low = msg.lower()
                if "collection failure" in low or (not cls and "collect" in low):
                    phase = "collection"
                elif "teardown" in low:
                    phase = "teardown"
                else:
                    phase = "setup"
            exc = _exc_type(msg, text)
            if phase == "collection" and not exc:
                exc = "CollectionError"
            break
        out.append(TestCaseOutcome(nodeid, outcome, phase, exc, msg[:500]))
    return out


# --------------------------------------------------------------------------
# Workspace helpers
# --------------------------------------------------------------------------

_DELETE_FILE = "_DELETE"
_COPY_IGNORE = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".pytest_cache", ".ruff_cache")


def apply_overlay(overlay: str | os.PathLike, dest: str | os.PathLike) -> None:
    """Copy ``overlay`` over ``dest``. A top-level ``_DELETE`` file lists paths to remove."""
    overlay, dest = Path(overlay), Path(dest)
    delete = overlay / _DELETE_FILE
    if delete.exists():
        for line in delete.read_text().splitlines():
            rel = line.strip()
            if not rel or rel.startswith("#"):
                continue
            target = (dest / rel).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise ValueError(f"_DELETE entry escapes workspace: {rel}")
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
    for src in overlay.rglob("*"):
        rel = src.relative_to(overlay)
        if rel.as_posix() == _DELETE_FILE or "__pycache__" in rel.parts:
            continue
        tgt = dest / rel
        if src.is_dir():
            tgt.mkdir(parents=True, exist_ok=True)
        else:
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tgt)


class UnsafeWorkspaceError(ValueError):
    """Agent-created links cannot safely be handed to an unsandboxed grader."""


def unsafe_workspace_symlinks(workspace: str | os.PathLike) -> list[str]:
    """Find external, dangling, cyclic and directory links without traversing them.

    Directory links are refused: even internal links can form traversal cycles
    through multiple directories. Internal file links remain supported.
    """
    workspace = Path(workspace)
    if workspace.is_symlink():
        return [f"workspace root -> {os.readlink(workspace)}"]
    root = workspace.resolve()
    unsafe = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if name != ".git"]
        for name in dirs + files:
            path = Path(directory) / name
            if not path.is_symlink():
                continue
            try:
                resolved = path.resolve(strict=True)
                safe = resolved.is_relative_to(root) and resolved.is_file()
            except (OSError, RuntimeError):
                safe = False
            if not safe:
                unsafe.append(f"{path.relative_to(root)} -> {os.readlink(path)}")
    return unsafe


def validate_workspace(workspace: str | os.PathLike) -> None:
    unsafe = unsafe_workspace_symlinks(workspace)
    if unsafe:
        raise UnsafeWorkspaceError("unsafe workspace symlinks: " + "; ".join(unsafe[:10]))


def copy_workspace(
    workspace: str | os.PathLike,
    overlays: Iterable[str | os.PathLike] = (),
    dest: str | os.PathLike | None = None,
) -> Path:
    """Copy ``workspace`` (without ``.git``/caches) to a temp dir and apply ``overlays`` in order.

    Typical use: swap a hidden buggy DAG under the agent's tests::

        buggy = g.copy_workspace(ws, [CASE_DIR / "hidden_bugs" / "drops_nulls"])
        res = g.run_pytest(py, buggy, ["tests"])
        grader.primary("tests catch drops_nulls", res.caught_bug, res.summary())
    """
    validate_workspace(workspace)
    target = Path(dest) if dest else Path(tempfile.mkdtemp(prefix="eval-ws-")).resolve() / "ws"
    if target.exists() or target.is_symlink():
        raise UnsafeWorkspaceError("workspace copy destination already exists")
    # The caller chooses the destination, but agents can plant its components.
    # Resolve the trusted system temp aliases only for our own fresh temp dir.
    if any(parent.is_symlink() for parent in target.absolute().parents):
        raise UnsafeWorkspaceError("workspace copy destination has a symlink ancestor")
    # Never let copytree dereference agent links. Rewrite safe file links into
    # the copy, including absolute links whose original target was in workspace.
    shutil.copytree(workspace, target, ignore=_COPY_IGNORE, dirs_exist_ok=True, symlinks=True)
    root = Path(workspace).resolve()
    for directory, _dirs, files in os.walk(target, followlinks=False):
        for name in files:
            link = Path(directory) / name
            if link.is_symlink():
                source = root / link.relative_to(target)
                local_target = target / source.resolve(strict=True).relative_to(root)
                link.unlink()
                link.symlink_to(os.path.relpath(local_target, link.parent))
    for ov in overlays:
        apply_overlay(ov, target)
    validate_workspace(target)
    return target


# --------------------------------------------------------------------------
# Agent event stream: altimate-code ``--format json`` or Claude Code
# ``--output-format stream-json --verbose``. Every parser below accepts either;
# :func:`is_claude_stream` tells them apart.
# --------------------------------------------------------------------------

#: Claude Code tool names -> the lowercase altimate-code names the parsers and
#: the contamination scan use. Any other tool is lowercased.
CLAUDE_TOOL_ALIASES = {"Bash": "bash", "Read": "read", "Edit": "edit", "MultiEdit": "multiedit", "Write": "write",
                       "NotebookEdit": "notebookedit", "Glob": "glob", "Grep": "grep", "Skill": "skill",
                       "Task": "task", "Agent": "task", "WebFetch": "webfetch", "WebSearch": "websearch"}
#: Claude Code ``result`` subtype for a run stopped by ``--max-turns``.
CLAUDE_MAX_TURNS_SUBTYPE = "error_max_turns"


def load_events(path: str | os.PathLike | None) -> list[dict]:
    """Read a JSONL event stream; non-JSON lines are ignored; missing file -> []."""
    if not path or not Path(path).exists():
        return []
    events = []
    for line in Path(path).read_text(errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


def is_claude_stream(events: list[dict]) -> bool:
    """True for a Claude Code stream-json transcript (init/assistant/user/result events)."""
    for e in events:
        t = e.get("type")
        if t == "system" and e.get("subtype") == "init":
            return True
        if t in ("assistant", "user") and isinstance(e.get("message"), dict):
            return True
        if t == "result" and ("total_cost_usd" in e or "num_turns" in e):
            return True
    return False


def _content_text(content: Any) -> str:
    """Text of a tool_result ``content`` (a string or a list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text") or "") for b in content if isinstance(b, dict))
    return ""


def _claude_tool_uses(events: list[dict]) -> list[dict]:
    results: dict[str, tuple[str, bool]] = {}
    for e in events:
        if e.get("type") != "user":
            continue
        for b in (e.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                results[str(b.get("tool_use_id"))] = (_content_text(b.get("content")), bool(b.get("is_error")))
    out, seen = [], set()
    for e in events:
        if e.get("type") != "assistant":
            continue
        for b in (e.get("message") or {}).get("content") or []:
            if not isinstance(b, dict) or b.get("type") != "tool_use" or b.get("id") in seen:
                continue
            seen.add(b.get("id"))
            raw = str(b.get("name") or "")
            text, is_error = results.get(str(b.get("id")), ("", False))
            status = "error" if is_error else ("completed" if str(b.get("id")) in results else "pending")
            out.append({"tool": CLAUDE_TOOL_ALIASES.get(raw, raw.lower()), "raw_tool": raw,
                        "input": b.get("input") if isinstance(b.get("input"), dict) else {},
                        "status": status, "metadata": {}, "output": text,
                        "subagent": e.get("parent_tool_use_id")})
    return out


def tool_uses(events: list[dict], tool: str | None = None) -> list[dict]:
    """``[{"tool", "input", "status", "metadata", "output"}]`` for tool calls.

    ``tool`` uses the lowercase altimate-code names; Claude Code names are mapped
    with :data:`CLAUDE_TOOL_ALIASES` (``Bash`` -> ``bash``, ``Skill`` -> ``skill``).
    """
    if is_claude_stream(events):
        return [u for u in _claude_tool_uses(events) if not tool or u["tool"] == tool]
    out = []
    for e in events:
        if e.get("type") != "tool_use":
            continue
        part = e.get("part") or {}
        state = part.get("state") or {}
        name = part.get("tool")
        if tool and name != tool:
            continue
        out.append(
            {
                "tool": name,
                "input": state.get("input") or {},
                "status": state.get("status"),
                "metadata": state.get("metadata") or {},
                "output": state.get("output") if isinstance(state.get("output"), str) else "",
            }
        )
    return out


def skill_invocations(events: list[dict]) -> list[dict]:
    """``[{"name", "origin", "status"}]`` for on-demand ``skill`` tool calls."""
    return [
        {
            # altimate-code: ``{"name": ...}``; Claude Code: ``{"skill": ...}``
            "name": (u["input"] or {}).get("name") or (u["input"] or {}).get("skill"),
            "origin": u["metadata"].get("skillOrigin") or u["metadata"].get("source"),
            "status": u["status"],
        }
        for u in tool_uses(events, "skill")
    ]


def bash_commands(events: list[dict]) -> list[str]:
    """Shell commands the agent executed (bash tool ``input.command``)."""
    return [str(u["input"].get("command", "")) for u in tool_uses(events, "bash")]


def ran_command_matching(events: list[dict], pattern: str, flags: int = re.I) -> bool:
    """True when any executed bash command matches ``pattern`` (``re.search``)."""
    rx = re.compile(pattern, flags)
    return any(rx.search(c) for c in bash_commands(events))


def edited_files(events: list[dict]) -> list[str]:
    """File paths touched by edit/write/apply_patch tools (deduplicated, in order)."""
    seen: list[str] = []
    for u in tool_uses(events):
        if u["tool"] not in ("edit", "write", "apply_patch", "multiedit", "patch", "notebookedit"):
            continue
        inp = u["input"]
        for key in ("filePath", "file_path", "path", "notebook_path"):
            if inp.get(key) and inp[key] not in seen:
                seen.append(inp[key])
    return seen


# --------------------------------------------------------------------------
# Cost
# --------------------------------------------------------------------------

#: USD per 1M tokens: (input, output, cache read, 5-minute cache write).
#: Sources: Anthropic list prices from the claude-api skill model table (cached
#: 2026-09-25; https://platform.claude.com/docs/en/about-claude/pricing) and
#: altimate-code's model metadata (~/.cache/altimate-code/models.json, entries
#: ``google-vertex-anthropic/<id>``), which agree for every row. Long-context
#: (>200k prompt) tiers are not modelled; eval prompts stay below 200k.
MODEL_PRICING_PER_MTOK: dict[str, tuple[float, float, float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0, 0.10, 1.25),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30, 3.75),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.50),
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.00),
    "claude-fable-5-1": (10.0, 50.0, 0.25, 12.50),
}
# Fallback price multiples relative to the uncached input price, for models
# without a pricing row (valid for Claude models up to the 4.x generation; newer
# models have cheaper cache reads, so they need a pricing row).
_OUTPUT_X, _CACHE_READ_X, _CACHE_WRITE_X = 5.0, 0.1, 1.25
#: provider prefix and altimate-code version prefix whose step_finish events
#: double count cached prompt tokens (see :func:`step_cost`).
DOUBLE_COUNT_PROVIDER = "google-vertex-anthropic/"
DOUBLE_COUNT_VERSION_PREFIX = "0.12."
_MATCH_TOLERANCE = 0.02


def model_key(model: str | None) -> str:
    """``provider/claude-x-y@ver`` -> ``claude-x-y`` (date suffixes dropped)."""
    name = str(model or "").split("/")[-1].split("@")[0]
    return re.sub(r"-\d{8}$", "", name)


def model_pricing(model: str | None) -> tuple[float, float, float, float] | None:
    return MODEL_PRICING_PER_MTOK.get(model_key(model))


def cache_correction_applies(model: str | None, altimate_version: str | None) -> bool:
    """True for the provider/version combination known to double count cached tokens."""
    return (str(model or "").startswith(DOUBLE_COUNT_PROVIDER)
            and str(altimate_version or "").strip().startswith(DOUBLE_COUNT_VERSION_PREFIX))


def _step_tokens(part: dict) -> tuple[int, int, int, int]:
    tk = part.get("tokens") or {}
    cache = tk.get("cache") or {}
    out = int(tk.get("output") or 0) + int(tk.get("reasoning") or 0)
    return int(tk.get("input") or 0), out, int(cache.get("read") or 0), int(cache.get("write") or 0)


def list_price_cost(part: dict, model: str | None, input_includes_cache: bool) -> float | None:
    """Cost of a step at list prices, or None without a pricing row.

    ``input_includes_cache``: ``tokens.input`` counts cache reads/writes too, so
    only ``input - read - write`` is charged at the uncached rate.
    """
    price = model_pricing(model)
    if price is None:
        return None
    inp, out, read, write = _step_tokens(part)
    uncached = max(0, inp - read - write) if input_includes_cache else inp
    p_in, p_out, p_read, p_write = price
    return (uncached * p_in + out * p_out + read * p_read + write * p_write) / 1e6


def step_double_counted(part: dict, model: str | None) -> bool | None:
    """Whether the reported cost charges cached tokens twice (None: unknown model or no cache)."""
    reported = float(part.get("cost") or 0)
    inp, _, read, write = _step_tokens(part)
    if reported <= 0 or not (read or write) or inp < read + write:
        return None
    naive = list_price_cost(part, model, input_includes_cache=False)
    if naive is None:
        return None
    return abs(reported - naive) <= max(1e-6, _MATCH_TOLERANCE * naive)


def step_cost(part: dict, model: str | None = None, correct: bool = True) -> float:
    """Cost of one ``step_finish`` part, corrected for cached-token double counting.

    altimate-code 0.12.x with google-vertex-anthropic reports ``tokens.input`` as
    the full prompt size including cache reads/writes, and prices all of it at
    the uncached input rate on top of the cache charges (~3-10x inflation once
    the prompt is cached). The correction only runs when ``correct`` is true
    (callers pass :func:`cache_correction_applies`) and the step shows the
    pattern (``input >= cache.read + cache.write``):

    - with a pricing row for ``model``: the step is re-priced without the
      double count, but only if the reported cost matches the double-counted
      price; a model whose reported cost does not double count keeps it.
    - without a pricing row: the cached part is removed using the pre-5.x
      Anthropic price ratios.

    Otherwise the reported cost is returned unchanged.
    """
    reported = float(part.get("cost") or 0)
    inp, out, read, write = _step_tokens(part)
    if not correct or reported <= 0 or not (read or write) or inp < read + write:
        return reported
    if model_pricing(model) is not None:
        if step_double_counted(part, model):
            return float(list_price_cost(part, model, input_includes_cache=True))
        return reported
    rest = _OUTPUT_X * out + _CACHE_READ_X * read + _CACHE_WRITE_X * write
    return reported * ((inp - read - write) + rest) / (inp + rest)


def claude_result(events: list[dict]) -> dict | None:
    """The last Claude Code ``result`` event (absent when the run was killed)."""
    found = [e for e in events if e.get("type") == "result"]
    return found[-1] if found else None


def _claude_messages(events: list[dict], subagents: bool = False) -> dict[str, dict]:
    """Real model messages by id with their usage (a message spans several events; the
    largest value of each usage field wins). Synthetic messages (local commands,
    API errors) are skipped, and subagent messages (``parent_tool_use_id``) unless
    ``subagents``."""
    msgs: dict[str, dict] = {}
    for e in events:
        if e.get("type") != "assistant" or (e.get("parent_tool_use_id") and not subagents):
            continue
        m = e.get("message") or {}
        if m.get("model") == "<synthetic>" or not m.get("id"):
            continue
        u = m.get("usage") or {}
        cur = msgs.setdefault(m["id"], {"model": m.get("model")})
        cc = u.get("cache_creation") or {}
        for key, val in (("input", u.get("input_tokens")), ("output", u.get("output_tokens")),
                         ("cache_read", u.get("cache_read_input_tokens")),
                         ("cache_write", u.get("cache_creation_input_tokens")),
                         ("cache_write_1h", cc.get("ephemeral_1h_input_tokens"))):
            cur[key] = max(int(cur.get(key) or 0), int(val or 0))
    return msgs


def claude_list_cost(tokens: dict, model: str | None) -> float | None:
    """API-equivalent cost of Claude Code tokens at list prices (1-hour cache writes at
    2x input, 5-minute writes at the table rate); None without a pricing row."""
    price = model_pricing(model)
    if price is None:
        return None
    p_in, p_out, p_read, p_write = price
    w1h = min(int(tokens.get("cache_write_1h") or 0), int(tokens.get("cache_write") or 0))
    w5m = int(tokens.get("cache_write") or 0) - w1h
    return (int(tokens.get("input") or 0) * p_in + int(tokens.get("output") or 0) * p_out
            + int(tokens.get("cache_read") or 0) * p_read + w5m * p_write + w1h * 2 * p_in) / 1e6


def claude_running_cost(events: list[dict], model: str | None) -> float:
    """Cost so far: the final ``total_cost_usd`` once the result event exists, else the
    list-price estimate of the messages seen, subagents included (used for per-run
    caps while running and for runs killed before their result)."""
    res = claude_result(events)
    if res is not None and res.get("total_cost_usd") is not None:
        return float(res["total_cost_usd"])
    return sum(claude_list_cost(m, m.get("model") or model) or claude_list_cost(m, model) or 0.0
               for m in _claude_messages(events, subagents=True).values())


def _claude_usage(events: list[dict], model: str | None) -> dict:
    res = claude_result(events)
    msgs = _claude_messages(events)
    tot = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0, "total": 0}
    if res is not None:
        u = res.get("usage") or {}
        cc = u.get("cache_creation") or {}
        toks = {"input": u.get("input_tokens"), "output": u.get("output_tokens"),
                "cache_read": u.get("cache_read_input_tokens"), "cache_write": u.get("cache_creation_input_tokens"),
                "cache_write_1h": cc.get("ephemeral_1h_input_tokens")}
        toks = {k: int(v or 0) for k, v in toks.items()}
        tot["reasoning"] = int((u.get("output_tokens_details") or {}).get("thinking_tokens") or 0)
        steps = int(res.get("num_turns") or 0)
        source = "result"
    else:
        toks = {k: sum(int(m.get(k) or 0) for m in _claude_messages(events, subagents=True).values())
                for k in ("input", "output", "cache_read", "cache_write", "cache_write_1h")}
        steps = len(msgs)
        source = "estimate"
    for k in ("input", "output", "cache_read", "cache_write"):
        tot[k] = toks[k]
    tot["total"] = toks["input"] + toks["output"] + toks["cache_read"] + toks["cache_write"]
    cost = claude_running_cost(events, model)
    list_cost = claude_list_cost(toks, model)
    return {"tokens": tot, "cost_usd": round(cost, 6), "cost_usd_equivalent": round(cost, 6),
            "cost_reported_usd": round(float((res or {}).get("total_cost_usd") or 0), 6),
            "cost_list_price_usd": None if list_cost is None else round(list_cost, 6),
            "cost_source": source, "double_counted_steps": 0, "steps": steps,
            "model_usage": (res or {}).get("modelUsage")}


def model_steps(events: list[dict]) -> int:
    """Completed model steps: altimate-code ``step_finish`` events, or real Claude Code
    assistant messages (local commands and API-error placeholders do not count)."""
    if is_claude_stream(events):
        return len(_claude_messages(events))
    return sum(1 for e in events if e.get("type") == "step_finish")


def usage(events: list[dict], model: str | None = None, correct: bool = True) -> dict:
    """Token and cost totals summed over ``step_finish`` events.

    For a Claude Code stream the totals come from its ``result`` event:
    ``cost_usd`` = ``cost_usd_equivalent`` = ``total_cost_usd`` (API-equivalent;
    a subscription is not billed per token), estimated at list prices when the
    run was killed before it wrote a result.

    - ``cost_usd``: corrected with :func:`step_cost` (``correct`` gates it).
    - ``cost_reported_usd``: the raw sum altimate-code reported.
    - ``cost_list_price_usd``: recomputed from tokens at list prices (cache
      excluded from input when the step shows the double-count pattern);
      ``None`` without a pricing row. Used to audit the correction.
    - ``double_counted_steps``: steps whose reported cost matched the
      double-counted price.
    """
    if is_claude_stream(events):
        return _claude_usage(events, model)
    tot = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0, "total": 0}
    cost, reported, steps, doubled = 0.0, 0.0, 0, 0
    list_cost: float | None = 0.0 if model_pricing(model) else None
    for e in events:
        if e.get("type") != "step_finish":
            continue
        part = e.get("part") or {}
        steps += 1
        cost += step_cost(part, model, correct)
        reported += float(part.get("cost") or 0)
        if step_double_counted(part, model):
            doubled += 1
        if list_cost is not None:
            inp, _, read, write = _step_tokens(part)
            # Only the double-counting provider/version includes cached tokens in ``input``.
            list_cost += list_price_cost(
                part, model, input_includes_cache=correct and inp >= read + write and bool(read or write))
        tk = part.get("tokens") or {}
        cache = tk.get("cache") or {}
        tot["input"] += int(tk.get("input") or 0)
        tot["output"] += int(tk.get("output") or 0)
        tot["reasoning"] += int(tk.get("reasoning") or 0)
        tot["cache_read"] += int(cache.get("read") or 0)
        tot["cache_write"] += int(cache.get("write") or 0)
        tot["total"] += int(tk.get("total") or 0)
    return {"tokens": tot, "cost_usd": round(cost, 6), "cost_reported_usd": round(reported, 6),
            "cost_list_price_usd": None if list_cost is None else round(list_cost, 6),
            "double_counted_steps": doubled, "steps": steps}


def termination(events: list[dict]) -> dict | None:
    """The final ``termination`` event (why_model_stopped / why_harness_stopped / done_reason).

    For Claude Code it is derived from the ``result`` event: ``error_max_turns`` maps
    to ``why_harness_stopped="budget-exhausted"`` (like altimate-code's turn limit),
    any other ``is_error`` result to ``"error"``.
    """
    if is_claude_stream(events):
        res = claude_result(events)
        if res is None:
            return None
        sub = res.get("subtype")
        why = ("budget-exhausted" if sub == CLAUDE_MAX_TURNS_SUBTYPE
               else "error" if res.get("is_error") else "completed")
        return {"type": "termination", "why_harness_stopped": why, "why_model_stopped": res.get("stop_reason"),
                "done_reason": sub, "terminal_reason": res.get("terminal_reason"),
                "api_error_status": res.get("api_error_status"), "num_turns": res.get("num_turns")}
    found = [e for e in events if e.get("type") == "termination"]
    return found[-1] if found else None


def _claude_error_messages(events: list[dict]) -> list[str]:
    out = []
    for e in events:
        t = e.get("type")
        if t == "result" and e.get("is_error"):
            detail = e.get("result") or "; ".join(str(x) for x in e.get("errors") or []) or ""
            status = e.get("api_error_status")
            out.append(f"{e.get('subtype')}{f' (HTTP {status})' if status else ''}: {str(detail)[:400]}")
        elif t == "assistant":
            m = e.get("message") or {}
            err = e.get("error") or m.get("error")
            if m.get("model") == "<synthetic>" or err:
                text = _content_text(m.get("content"))
                if err or text.startswith("API Error") or "limit" in text.lower():
                    out.append(f"{err or 'api_error'}: {text[:400]}")
        elif t == "system" and e.get("subtype") == "api_retry":
            out.append(f"api_retry {e.get('attempt')}/{e.get('max_retries')} (HTTP {e.get('error_status')}): "
                       f"{str(e.get('error'))[:300]}")
        elif t == "rate_limit_event":
            info = e.get("rate_limit_info") or {}
            if info.get("status") == "rejected":
                out.append(f"usage limit reached: rate_limit_event rejected ({info.get('rateLimitType')}, "
                           f"resetsAt {info.get('resetsAt')})")
    return out


def error_messages(events: list[dict]) -> list[str]:
    """Human-readable messages of ``error`` events (Claude Code: error results, API
    error placeholders, ``api_retry`` events and rejected rate-limit events)."""
    if is_claude_stream(events):
        return _claude_error_messages(events)
    out = []
    for e in events:
        if e.get("type") != "error":
            continue
        err = e.get("error")
        if isinstance(err, dict):
            data = err.get("data") if isinstance(err.get("data"), dict) else {}
            out.append(f"{err.get('name', '')}: {data.get('message') or err.get('message') or json.dumps(err)[:400]}")
        else:
            out.append(str(err or e.get("message") or json.dumps(e)[:400]))
    return out


# --------------------------------------------------------------------------
# Checks and result writing
# --------------------------------------------------------------------------


@dataclass
class Check:
    name: str
    kind: str  # "primary" | "secondary"
    passed: bool
    detail: str = ""


class Grader:
    """Collects checks and writes the grade result JSON.

    ``primary`` = behavioral correctness (import, run, data, schedule, tests
    that catch bugs). ``secondary`` = process/style (verification commands run,
    ruff AIR clean, no deprecation warnings).
    """

    MAX_DETAIL = 4000

    def __init__(self) -> None:
        self.checks: list[Check] = []

    def add(self, name: str, passed: bool, detail: str = "", kind: str = "primary") -> bool:
        if kind not in ("primary", "secondary"):
            raise ValueError(f"kind must be primary|secondary, got {kind!r}")
        detail = str(detail)
        if len(detail) > self.MAX_DETAIL:
            detail = detail[: self.MAX_DETAIL // 2] + "\n...\n" + detail[-self.MAX_DETAIL // 2:]
        self.checks.append(Check(name, kind, bool(passed), detail))
        return bool(passed)

    def primary(self, name: str, passed: bool, detail: str = "") -> bool:
        return self.add(name, passed, detail, "primary")

    def secondary(self, name: str, passed: bool, detail: str = "") -> bool:
        return self.add(name, passed, detail, "secondary")

    def run(self, name: str, fn: Callable[[], Any], kind: str = "primary") -> bool:
        """Record ``fn()``: truthy passes; ``(passed, detail)`` tuples are unpacked;
        an exception is a failed check with the traceback as detail."""
        import traceback

        try:
            value = fn()
        except Exception:  # noqa: BLE001 - agent code may crash probes; that is a failed check
            return self.add(name, False, traceback.format_exc(limit=8), kind)
        if isinstance(value, tuple) and len(value) == 2:
            return self.add(name, bool(value[0]), str(value[1]), kind)
        return self.add(name, bool(value), "", kind)

    def result(self) -> dict:
        return build_result(self.checks)

    def write(self, out: str | os.PathLike) -> dict:
        res = self.result()
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(res, indent=2))
        return res


def build_result(checks: list[Check]) -> dict:
    """Result dict: ``checks``, ``primary_pass``, ``primary_score``, ``secondary_score``.

    ``primary_pass`` is False when there are no primary checks (a grader must
    assert something). ``secondary_score`` is ``None`` without secondary checks.
    """
    prim = [c for c in checks if c.kind == "primary"]
    sec = [c for c in checks if c.kind == "secondary"]
    return {
        "checks": [asdict(c) for c in checks],
        "primary_pass": bool(prim) and all(c.passed for c in prim),
        "primary_score": (sum(c.passed for c in prim) / len(prim)) if prim else 0.0,
        "secondary_score": (sum(c.passed for c in sec) / len(sec)) if sec else None,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Standard grade.py CLI: ``--workspace DIR --events EVENTS.jsonl --out RESULT.json``."""
    ap = argparse.ArgumentParser(description="Grade an Airflow eval workspace")
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--events", type=Path, default=None, help="agent JSONL events (optional)")
    ap.add_argument("--out", required=True, type=Path)
    ns = ap.parse_args(argv)
    ns.workspace = ns.workspace.resolve()
    return ns


# --------------------------------------------------------------------------
# Standard secondary checks (optional convenience for case authors)
# --------------------------------------------------------------------------

#: default "the agent verified its work" command patterns.
VERIFY_PATTERNS = (
    r"\bairflow\s+dags\s+(test|list-import-errors|list|reserialize)\b",
    r"\bpytest\b",
    r"\bDagBag\b",
    r"\bdag\.test\(",
    r"\bruff\b.*\bAIR\b",
    r"\bpython[0-9.]*\s+\S*dags/\S+\.py",
)


def standard_secondary_checks(
    grader: Grader,
    env_py: str | None,
    workspace: str | os.PathLike,
    events: list[dict],
    import_result: dict | None = None,
    verify_patterns: Sequence[str] = VERIFY_PATTERNS,
    ruff_paths: Sequence[str] = ("dags",),
    ruff_select: str | None = None,
) -> None:
    """Add the three standard secondary checks: verification commands ran,
    ruff AIR clean, and no deprecation warnings while parsing the DAGs.

    ``ruff_select`` defaults to :func:`air_select_for` the parsed Airflow version,
    so a correct 2.x project is not penalised by Airflow-3 migration rules."""
    imp = import_result if import_result is not None else import_dags(env_py, workspace)
    select = ruff_select or air_select_for(imp.get("airflow_version"))
    matched = [p for p in verify_patterns if ran_command_matching(events, p)]
    grader.secondary("ran verification commands", bool(matched),
                     f"matched: {matched}" if matched else f"{len(bash_commands(events))} bash commands, none verifying")
    try:
        findings = ruff_air(env_py, workspace, ruff_paths, select=select)
        grader.secondary(f"ruff {select} clean", not findings,
                         "; ".join(f"{f['filename']}:{f['line']} {f['code']}" for f in findings[:20]))
    except RuntimeError as exc:
        grader.secondary(f"ruff {select} clean", False, str(exc))
    deps = deprecation_warnings(imp)
    grader.secondary("no deprecation warnings", not deps,
                     "; ".join(f"{w['filename']}:{w['lineno']} {w['category']}: {w['message'][:120]}" for w in deps[:10]))
