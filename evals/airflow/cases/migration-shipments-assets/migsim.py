"""Migration grading helpers: replay *scheduled* DAG runs in 2.11 and 3.3.

``airflow dags test <logical_date>`` gives a run the data interval of a
*manual* trigger, which differs from what the scheduler assigns (for example
``ds`` under a cron data-interval timetable). The migration graders need the
scheduler's view: "the run that fires at T processes X". ``simulate`` finds the
scheduled run whose ``run_after`` equals T via the DAG's own timetable, then
executes it in-process with ``dag.test`` while forcing that run's logical date
and data interval.

On Airflow 3 it can also emulate the worker's metadata-DB block (Airflow 3 task
processes cannot open ORM sessions; ``dag.test`` runs in-process and does not
enforce this). Any ORM session opened while DAG-project code is on the call
stack, other than through the Task SDK's execution API, raises the same
RuntimeError a real worker raises.

This file is identical in every ``migration-*`` case directory.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(Path(__file__).resolve().parents[3] / "harness")))
import grading as g  # noqa: E402

_MARK = "__MIGSIM_RESULT__"

_PROBE = r'''
import json, os, sys
P = json.loads(os.environ["MIGSIM_PARAMS"])
import airflow, pendulum
MAJOR = int(airflow.__version__.split(".")[0])
RESULT = {"airflow_version": airflow.__version__, "runs": [], "error": None}

def _roots():
    ws = P["workspace"]
    return tuple({ws.rstrip("/") + "/", os.path.realpath(ws).rstrip("/") + "/"})

def install_orm_block():
    from airflow import settings
    roots = _roots()
    MSG = "Direct database access via the ORM is not allowed in Airflow 3.0"

    def in_project_code():
        f = sys._getframe(2)
        project = False
        while f is not None:
            fn = f.f_code.co_filename
            if "/airflow/api_fastapi/" in fn:
                return False
            if fn.startswith(roots):
                project = True
            f = f.f_back
        return project

    class Guard:
        def __init__(self, real):
            object.__setattr__(self, "_real", real)
        def __call__(self, *a, **k):
            if in_project_code():
                raise RuntimeError(MSG)
            return self._real(*a, **k)
        def __getattr__(self, name):
            if in_project_code():
                raise RuntimeError(MSG)
            return getattr(self._real, name)

    for attr in ("Session", "NonScopedSession"):
        real = getattr(settings, attr, None)
        if real is not None and not isinstance(real, Guard):
            setattr(settings, attr, Guard(real))

def load_dag(dag_id):
    folder = os.environ["AIRFLOW__CORE__DAGS_FOLDER"]
    if MAJOR >= 3:
        from airflow.dag_processing.dagbag import DagBag
        bag = DagBag(dag_folder=folder)
    else:
        from airflow.models import DagBag
        bag = DagBag(dag_folder=folder, include_examples=False)
    if dag_id not in bag.dags:
        raise KeyError(f"DAG {dag_id!r} not found; import errors: {bag.import_errors}")
    return bag.dags[dag_id]

def core_timetable(dag):
    try:
        from airflow.serialization.serialized_objects import coerce_to_core_timetable
    except ImportError:
        return dag.timetable
    return coerce_to_core_timetable(dag.timetable)

def find_run(dag, tt, run_after):
    from airflow.timetables.base import TimeRestriction
    target = pendulum.parse(run_after)
    restriction = TimeRestriction(earliest=dag.start_date, latest=None, catchup=True)
    last = None
    for _ in range(20000):
        info = tt.next_dagrun_info(last_automated_data_interval=last, restriction=restriction)
        if info is None or info.run_after > target:
            return None
        if info.run_after == target:
            return info
        last = info.data_interval
    return None

def task_states(dag_id, logical_date):
    from airflow.models.dagrun import DagRun
    from airflow.utils.session import create_session
    col = DagRun.logical_date if MAJOR >= 3 else DagRun.execution_date
    with create_session() as s:
        dr = s.query(DagRun).filter(DagRun.dag_id == dag_id, col == logical_date).one_or_none()
        if dr is None:
            return None, {}
        return (str(getattr(dr.state, "value", dr.state)),
                {ti.task_id if ti.map_index < 0 else f"{ti.task_id}[{ti.map_index}]":
                 str(getattr(ti.state, "value", ti.state)) for ti in dr.get_task_instances(session=s)})

def forgive_deadline_bug(row):
    """Airflow 3.3.2 bug: dag.test() (and so `airflow dags test`) crashes in
    DagRun.update_state for any DAG with a DeadlineAlert, after every task has
    succeeded ('dict' object has no attribute 'hex' on deadline_alert). The
    scheduler path is unaffected, so a run whose tasks all succeeded counts."""
    err = row.get("error") or ""
    tasks = row.get("tasks") or {}
    if "deadline_alert" in err and tasks and all(s == "success" for s in tasks.values()):
        row.pop("error")
        row["state"] = "success"
        row["note"] = "forgave Airflow 3.3.2 dag.test DeadlineAlert bug"

try:
    if P.get("block_orm") and MAJOR >= 3:
        install_orm_block()
    dag = load_dag(P["dag_id"])
    # A failing task must fail the run now instead of sleeping through retry_delay.
    for t in dag.tasks:
        t.retries = 0
    tt = core_timetable(dag)
    RESULT["timetable"] = type(tt).__name__
    for spec in P["runs"]:
        if isinstance(spec, dict):  # manual run, same semantics as `airflow dags test <dag> <date>`
            logical = pendulum.parse(spec["manual"])
            row = {"manual": spec["manual"], "logical_date": logical.isoformat()}
            RESULT["runs"].append(row)
            try:
                if MAJOR >= 3:
                    dag.test(logical_date=logical)
                else:
                    dag.test(execution_date=logical)
            except Exception as exc:  # noqa: BLE001
                row["error"] = f"dag.test raised {type(exc).__name__}: {exc}"
            row["state"], row["tasks"] = task_states(P["dag_id"], logical)
            forgive_deadline_bug(row)
            continue
        run_after = spec
        row = {"run_after": run_after}
        RESULT["runs"].append(row)
        info = find_run(dag, tt, run_after)
        if info is None:
            row["error"] = f"no scheduled run of {P['dag_id']} fires at {run_after} ({type(tt).__name__})"
            continue
        row.update(logical_date=info.logical_date.isoformat(),
                   start=info.data_interval.start.isoformat(), end=info.data_interval.end.isoformat())
        cls = type(tt)
        had = "infer_manual_data_interval" in cls.__dict__
        orig = cls.__dict__.get("infer_manual_data_interval")
        cls.infer_manual_data_interval = lambda self, *a, _di=info.data_interval, **k: _di
        try:
            if MAJOR >= 3:
                dag.test(logical_date=info.logical_date, run_after=info.run_after)
            else:
                dag.test(execution_date=info.logical_date)
        except Exception as exc:  # noqa: BLE001
            row["error"] = f"dag.test raised {type(exc).__name__}: {exc}"
        finally:
            if had:
                cls.infer_manual_data_interval = orig
            else:
                del cls.infer_manual_data_interval
        row["state"], row["tasks"] = task_states(P["dag_id"], info.logical_date)
        forgive_deadline_bug(row)
except Exception as exc:  # noqa: BLE001
    import traceback
    RESULT["error"] = traceback.format_exc(limit=6)
print("__MIGSIM_RESULT__" + json.dumps(RESULT, default=str))
'''


def simulate(env_py: str, workspace: Path, dag_id: str, runs: list, env: dict | None = None,
             block_orm: bool = False, timeout: float = 600) -> tuple[dict, str]:
    """Execute runs of ``dag_id`` in order against one metadata DB (task retries forced to 0).

    Each item of ``runs`` is either an ISO datetime T (the *scheduled* run that fires at T,
    with the logical date and data interval the DAG's timetable gives it) or
    ``manual(date)`` (what ``airflow dags test <dag_id> <date>`` does).
    Returns ``(result, log_tail)``; ``result["runs"][i]`` has ``logical_date, start, end,
    state, tasks, error``. ``state == "success"`` means the run passed."""
    env = dict(env if env is not None else g.airflow_env(workspace, env_py=env_py))
    db = g.ensure_db(env_py, env)
    if not db.ok:
        return {"runs": [], "error": "airflow db migrate failed: " + db.tail(20)}, db.tail(40)
    env["MIGSIM_PARAMS"] = json.dumps({"workspace": str(Path(workspace).resolve()), "dag_id": dag_id,
                                       "runs": list(runs), "block_orm": block_orm})
    proc = g.run_python_in_env(env_py, _PROBE, workspace, env=env, timeout=timeout)
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith(_MARK):
            return json.loads(line[len(_MARK):]), proc.tail(80)
    return {"runs": [], "error": "probe crashed: " + proc.tail(30)}, proc.tail(80)


def manual(logical_date: str) -> dict:
    """Run spec for :func:`simulate`: a manual run like ``airflow dags test <dag> <logical_date>``."""
    return {"manual": logical_date}


def runs_ok(result: dict) -> bool:
    runs = result.get("runs") or []
    return not result.get("error") and bool(runs) and all(
        r.get("state") == "success" and not r.get("error") for r in runs)


def describe(result: dict) -> str:
    if result.get("error"):
        return str(result["error"])[-1500:]
    return "; ".join(
        f"{r.get('run_after') or 'manual ' + str(r.get('manual'))}: " + (r.get("error") or f"state={r.get('state')} interval=[{r.get('start')}, {r.get('end')}]"
                                 f" failed={[t for t, s in (r.get('tasks') or {}).items() if s != 'success']}")
        for r in result.get("runs", []))


def snapshot(root: Path, rel: str = "output") -> dict[str, str]:
    """{relative path: text} for every file under ``root/rel`` (sorted, stripped)."""
    base = Path(root) / rel
    if not base.exists():
        return {}
    return {p.relative_to(base).as_posix(): p.read_text(errors="replace").strip()
            for p in sorted(base.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def original_workspace(case_dir: Path) -> Path:
    """Fresh copy of the pristine fixture (the Airflow 2 project)."""
    dest = Path(tempfile.mkdtemp(prefix="eval-orig-")) / "ws"
    shutil.copytree(Path(case_dir) / "fixture", dest,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
    return dest


def run_original(case_dir: Path, dag_id: str, runs: list, prepare=None) -> tuple[Path, dict, str]:
    """Run the pristine Airflow 2 project in the 2.11 env (see :func:`simulate` for ``runs``)."""
    ws = original_workspace(case_dir)
    if prepare:
        prepare(ws)
    py2 = g.env_python("2.11")
    result, log = simulate(py2, ws, dag_id, runs)
    return ws, result, log
