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

Extended for the ``hard-migration-*`` cases (identical in each of them): CLI/API
triggers without a logical date (``trigger``), scheduler-style asset/dataset
triggered runs that consume the recorded events (``asset_trigger``), and
multi-DAG replays against one metadata DB in one process (``replay``).
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
        # 2.x dag.test() does not write DAGs to the DB; dataset references
        # (needed to record and consume dataset events) come from this sync.
        if not bag.import_errors:
            bag.sync_to_db()
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

def _run_state(dr_id, session_factory):
    from airflow.models.dagrun import DagRun
    with session_factory() as s:
        dr = s.get(DagRun, dr_id)
        return (str(getattr(dr.state, "value", dr.state)),
                {ti.task_id if ti.map_index < 0 else f"{ti.task_id}[{ti.map_index}]":
                 str(getattr(ti.state, "value", ti.state)) for ti in dr.get_task_instances(session=s)})


def run_asset_triggered(dag, run_after, row):
    """Run ``dag`` the way the scheduler runs an asset/dataset-triggered DagRun at ``run_after``.

    Consumed events: every event of an asset the DAG is scheduled on that no earlier
    asset-triggered run of this DAG consumed (the grader triggers only once the DAG's
    condition is met). 3.x: logical_date and data_interval are None (scheduler code).
    2.x: execution_date = run_after and the interval comes from
    ``timetable.data_interval_for_events`` (scheduler code)."""
    from airflow.models.dagrun import DagRun
    from airflow.utils.session import create_session
    from airflow.utils.state import DagRunState
    from airflow.utils.types import DagRunType
    created = {}
    if MAJOR >= 3:
        from airflow.models import dagrun as drmod
        from airflow.models.asset import AssetEvent, DagScheduleAssetReference
        from airflow.utils.types import DagRunTriggeredByType
        orig = drmod.get_or_create_dagrun

        def patched(*, dag, session, **_):
            prev = session.query(DagRun).filter(DagRun.dag_id == dag.dag_id,
                                                DagRun.run_type == DagRunType.ASSET_TRIGGERED).all()
            consumed = {e.id for r in prev for e in r.consumed_asset_events}
            from sqlalchemy import or_
            from airflow.models.asset import AssetAliasModel, DagScheduleAssetAliasReference
            asset_ids = [r.asset_id for r in session.query(DagScheduleAssetReference)
                         .filter(DagScheduleAssetReference.dag_id == dag.dag_id).all()]
            via_alias = AssetEvent.source_aliases.any(AssetAliasModel.scheduled_dags.any(
                DagScheduleAssetAliasReference.dag_id == dag.dag_id))
            events = [e for e in session.query(AssetEvent).filter(or_(AssetEvent.asset_id.in_(asset_ids), via_alias))
                      .order_by(AssetEvent.timestamp, AssetEvent.id).all() if e.id not in consumed]
            dr = dag.create_dagrun(
                run_id=DagRun.generate_run_id(run_type=DagRunType.ASSET_TRIGGERED, logical_date=None,
                                              run_after=run_after),
                logical_date=None, data_interval=None, run_after=run_after,
                run_type=DagRunType.ASSET_TRIGGERED, triggered_by=DagRunTriggeredByType.ASSET,
                state=DagRunState.RUNNING, start_date=run_after, session=session, conf=None)
            dr.consumed_asset_events.extend(events)
            session.commit()
            created["id"], created["events"] = dr.id, len(events)
            return dr

        drmod.get_or_create_dagrun = patched
        try:
            dag.test(logical_date=None, run_after=run_after)
        finally:
            drmod.get_or_create_dagrun = orig
    else:
        from airflow.models import dag as dagmod
        from airflow.models.dataset import DagScheduleDatasetReference, DatasetEvent
        orig = dagmod._get_or_create_dagrun

        def patched(dag, conf, start_date, execution_date, run_id, session, data_interval=None):
            prev = session.query(DagRun).filter(DagRun.dag_id == dag.dag_id,
                                                DagRun.run_type == DagRunType.DATASET_TRIGGERED).all()
            consumed = {e.id for r in prev for e in r.consumed_dataset_events}
            ds_ids = [r.dataset_id for r in session.query(DagScheduleDatasetReference)
                      .filter(DagScheduleDatasetReference.dag_id == dag.dag_id).all()]
            events = [e for e in session.query(DatasetEvent).filter(DatasetEvent.dataset_id.in_(ds_ids))
                      .order_by(DatasetEvent.timestamp, DatasetEvent.id).all() if e.id not in consumed]
            interval = dag.timetable.data_interval_for_events(execution_date, events)
            dr = dag.create_dagrun(
                run_id=DagRun.generate_run_id(DagRunType.DATASET_TRIGGERED, execution_date),
                run_type=DagRunType.DATASET_TRIGGERED, execution_date=execution_date,
                data_interval=interval, state=DagRunState.RUNNING, start_date=execution_date,
                session=session, external_trigger=False)
            dr.consumed_dataset_events.extend(events)
            session.commit()
            created["id"], created["events"] = dr.id, len(events)
            return dr

        dagmod._get_or_create_dagrun = patched
        try:
            dag.test(execution_date=run_after)
        finally:
            dagmod._get_or_create_dagrun = orig
    row["events"] = created.get("events")
    if "id" not in created:
        row["error"] = "asset-triggered DagRun was not created"
        return None
    row["state"], row["tasks"] = _run_state(created["id"], create_session)
    return created["id"]


import contextlib


@contextlib.contextmanager
def run_kind(kind):
    """Make dag.test() create the DagRun the scheduler (kind="scheduled") or a CLI
    trigger (kind="trigger") would create: run_type, run_id format, triggered_by
    (3.x) / external_trigger (2.x). dag.test() alone makes every run MANUAL."""
    from airflow.models.dagrun import DagRun
    from airflow.utils.state import DagRunState
    from airflow.utils.types import DagRunType
    rtype = DagRunType.SCHEDULED if kind == "scheduled" else DagRunType.MANUAL
    if MAJOR >= 3:
        from airflow.models import dagrun as drmod
        from airflow.utils.types import DagRunTriggeredByType
        orig = drmod.get_or_create_dagrun

        def patched(*, dag, run_id, logical_date, data_interval, run_after, conf, session, start_date, **_):
            from sqlalchemy import select
            if logical_date is not None:
                old = session.scalar(select(DagRun).where(DagRun.dag_id == dag.dag_id,
                                                          DagRun.logical_date == logical_date))
                if old:
                    session.delete(old)
                    session.commit()
            return dag.create_dagrun(
                run_id=DagRun.generate_run_id(run_type=rtype, logical_date=logical_date, run_after=run_after),
                logical_date=logical_date, data_interval=data_interval, run_after=run_after, conf=conf,
                run_type=rtype,
                triggered_by=DagRunTriggeredByType.TIMETABLE if kind == "scheduled" else DagRunTriggeredByType.CLI,
                state=DagRunState.RUNNING, start_date=start_date or run_after, session=session)

        drmod.get_or_create_dagrun = patched
        try:
            yield
        finally:
            drmod.get_or_create_dagrun = orig
    else:
        from airflow.models import dag as dagmod
        orig = dagmod._get_or_create_dagrun

        def patched(dag, conf, start_date, execution_date, run_id, session, data_interval=None):
            from sqlalchemy import select
            old = session.scalar(select(DagRun).where(DagRun.dag_id == dag.dag_id,
                                                      DagRun.execution_date == execution_date))
            if old:
                session.delete(old)
                session.commit()
            return dag.create_dagrun(
                run_id=DagRun.generate_run_id(rtype, execution_date), run_type=rtype,
                execution_date=execution_date, data_interval=data_interval, state=DagRunState.RUNNING,
                start_date=start_date or execution_date, session=session, conf=conf,
                external_trigger=(kind == "trigger"))

        dagmod._get_or_create_dagrun = patched
        try:
            yield
        finally:
            dagmod._get_or_create_dagrun = orig


_DAGS = {}


def get_dag_tt(dag_id):
    if dag_id not in _DAGS:
        dag = load_dag(dag_id)
        # A failing task must fail the run now instead of sleeping through retry_delay.
        for t in dag.tasks:
            t.retries = 0
        _DAGS[dag_id] = (dag, core_timetable(dag))
    return _DAGS[dag_id]


def run_step(dag_id, spec):
    dag, tt = get_dag_tt(dag_id)
    RESULT.setdefault("timetables", {})[dag_id] = type(tt).__name__
    if isinstance(spec, dict) and "asset_trigger" in spec:
        run_after = pendulum.parse(spec["asset_trigger"])
        row = {"dag_id": dag_id, "asset_trigger": spec["asset_trigger"]}
        RESULT["runs"].append(row)
        try:
            run_asset_triggered(dag, run_after, row)
        except Exception as exc:  # noqa: BLE001
            import traceback
            row["error"] = f"asset-triggered run raised {type(exc).__name__}: {exc}\n" + traceback.format_exc(limit=4)
        return
    if isinstance(spec, dict) and "trigger" in spec:
        # CLI/API trigger (no logical date) at wall-clock T. 3.x: no logical date, run_after=T.
        # 2.x: logical date = T (the trigger time), interval inferred from T.
        run_after = pendulum.parse(spec["trigger"])
        row = {"dag_id": dag_id, "trigger": spec["trigger"]}
        RESULT["runs"].append(row)
        try:
            with run_kind("trigger"):
                if MAJOR >= 3:
                    dag.test(logical_date=None, run_after=run_after, run_conf=spec.get("conf"))
                else:
                    dag.test(execution_date=run_after, run_conf=spec.get("conf"))
        except Exception as exc:  # noqa: BLE001
            row["error"] = f"dag.test raised {type(exc).__name__}: {exc}"
        if MAJOR >= 3:
            from airflow.models.dagrun import DagRun
            from airflow.utils.session import create_session
            with create_session() as s:
                drs = s.query(DagRun).filter(DagRun.dag_id == dag_id, DagRun.run_after == run_after,
                                             DagRun.logical_date.is_(None)).all()
                if len(drs) == 1:
                    row["state"] = str(getattr(drs[0].state, "value", drs[0].state))
                    row["tasks"] = {ti.task_id if ti.map_index < 0 else f"{ti.task_id}[{ti.map_index}]":
                                    str(getattr(ti.state, "value", ti.state)) for ti in drs[0].get_task_instances(session=s)}
                else:
                    row["state"], row["tasks"] = None, {}
                    row.setdefault("error", f"found {len(drs)} runs with run_after={run_after}")
        else:
            row["state"], row["tasks"] = task_states(dag_id, run_after)
        forgive_deadline_bug(row)
        return
    if isinstance(spec, dict):  # manual run, same semantics as `airflow dags test <dag> <date>`
        logical = pendulum.parse(spec["manual"])
        row = {"dag_id": dag_id, "manual": spec["manual"], "logical_date": logical.isoformat()}
        RESULT["runs"].append(row)
        try:
            if MAJOR >= 3:
                dag.test(logical_date=logical)
            else:
                dag.test(execution_date=logical)
        except Exception as exc:  # noqa: BLE001
            row["error"] = f"dag.test raised {type(exc).__name__}: {exc}"
        row["state"], row["tasks"] = task_states(dag_id, logical)
        forgive_deadline_bug(row)
        return
    run_after = spec
    row = {"dag_id": dag_id, "run_after": run_after}
    RESULT["runs"].append(row)
    info = find_run(dag, tt, run_after)
    if info is None:
        row["error"] = f"no scheduled run of {dag_id} fires at {run_after} ({type(tt).__name__})"
        return
    row.update(logical_date=info.logical_date.isoformat(),
               start=info.data_interval.start.isoformat(), end=info.data_interval.end.isoformat())
    cls = type(tt)
    had = "infer_manual_data_interval" in cls.__dict__
    orig = cls.__dict__.get("infer_manual_data_interval")
    cls.infer_manual_data_interval = lambda self, *a, _di=info.data_interval, **k: _di
    try:
        with run_kind("scheduled"):
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
    row["state"], row["tasks"] = task_states(dag_id, info.logical_date)
    forgive_deadline_bug(row)


try:
    if P.get("block_orm") and MAJOR >= 3:
        install_orm_block()
    for dag_id, spec in P["steps"]:
        try:
            run_step(dag_id, spec)
        except Exception as exc:  # noqa: BLE001  (e.g. DAG missing): record, keep going
            import traceback
            RESULT["runs"].append({"dag_id": dag_id, "spec": spec,
                                   "error": traceback.format_exc(limit=4)[-1500:]})
except Exception as exc:  # noqa: BLE001
    import traceback
    RESULT["error"] = traceback.format_exc(limit=6)
print("__MIGSIM_RESULT__" + json.dumps(RESULT, default=str))
'''


def simulate(env_py: str, workspace: Path, dag_id: str, runs: list, env: dict | None = None,
             block_orm: bool = False, timeout: float = 600) -> tuple[dict, str]:
    """Execute runs of ``dag_id`` in order against one metadata DB (task retries forced to 0).

    Each item of ``runs`` is an ISO datetime T (the *scheduled* run that fires at T, with
    the logical date and data interval the DAG's timetable gives it), ``trigger(T)`` (a
    CLI/API trigger without a logical date at T), ``asset_trigger(T)`` (the scheduler's asset/dataset-triggered
    run at T) or ``manual(date)`` (what ``airflow dags test <dag_id> <date>`` does).
    Returns ``(result, log_tail)``; ``result["runs"][i]`` has ``logical_date, start, end,
    state, tasks, error``. ``state == "success"`` means the run passed."""
    return replay(env_py, workspace, [[dag_id, r] for r in runs], env=env, block_orm=block_orm,
                  timeout=timeout)


def replay(env_py: str, workspace: Path, steps: list, env: dict | None = None,
           block_orm: bool = False, timeout: float = 900) -> tuple[dict, str]:
    """Like :func:`simulate`, for ``steps = [[dag_id, run_spec], ...]`` across DAGs, in one process."""
    env = dict(env if env is not None else g.airflow_env(workspace, env_py=env_py))
    db = g.ensure_db(env_py, env)
    if not db.ok:
        return {"runs": [], "error": "airflow db migrate failed: " + db.tail(20)}, db.tail(40)
    env["MIGSIM_PARAMS"] = json.dumps({"workspace": str(Path(workspace).resolve()),
                                       "steps": [list(s) for s in steps], "block_orm": block_orm})
    proc = g.run_python_in_env(env_py, _PROBE, workspace, env=env, timeout=timeout)
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith(_MARK):
            return json.loads(line[len(_MARK):]), proc.tail(80)
    return {"runs": [], "error": "probe crashed: " + proc.tail(30)}, proc.tail(80)


def asset_trigger(run_after: str) -> dict:
    """Run spec: the asset/dataset-triggered run the scheduler creates at ``run_after``,
    consuming every event of the DAG's assets not consumed by an earlier such run."""
    return {"asset_trigger": run_after}


def trigger(run_after: str, conf: dict | None = None) -> dict:
    """Run spec: a CLI/API trigger (no logical date) at wall-clock ``run_after`` with no logical date
    (3.x: ``dag.test(logical_date=None, run_after=T)``; 2.x: logical date = T),
    optionally "with config" (``dag_run.conf``)."""
    return {"trigger": run_after, "conf": conf}


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
    def label(r):
        for key, name in (("run_after", "scheduled"), ("trigger", "CLI trigger"),
                          ("asset_trigger", "asset-triggered"), ("manual", "dags test")):
            if r.get(key):
                return f"{r.get('dag_id', '')} {name} {r[key]}".strip()
        return f"{r.get('dag_id', '')} {r.get('spec', '?')}"
    return "; ".join(
        f"{label(r)}: " + (str(r.get("error"))[-1200:] if r.get("error") else
                           f"state={r.get('state')} failed={[t for t, s in (r.get('tasks') or {}).items() if s != 'success']}")
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


# ---------------------------------------------------------------------------
# Whole-project comparison grading shared by the hard-migration-* cases.

_SCHEDULE_PROBE = r"""
from airflow.timetables.base import TimeRestriction

def cond(obj):
    if "Alias" in type(obj).__name__:  # 2.x: _DatasetAliasCondition (an "any" of resolved datasets)
        return "alias:" + obj.name
    if hasattr(obj, "objects"):
        kind = "all" if "All" in type(obj).__name__ else "any"
        parts = []
        for o in obj.objects:  # flatten nested groups of the same kind
            c = cond(o)
            parts.extend(c[kind] if isinstance(c, dict) and kind in c else [c])
        if len(parts) == 1:  # [x], x, any(x) and all(x) are the same condition
            return parts[0]
        return {kind: sorted(parts, key=repr)}
    return getattr(obj, "uri", None) or repr(obj)

out = {}
for dag_id in DAG_IDS:
    try:
        dag = get_dag(dag_id)
    except Exception as exc:
        out[dag_id] = {"error": repr(exc)[:300]}
        continue
    tt = core_timetable(dag)
    c = None
    if type(tt).__name__ in ("AssetTriggeredTimetable", "DatasetTriggeredTimetable"):
        c = getattr(tt, "asset_condition", None) or getattr(tt, "dataset_condition", None)
    row = {"catchup": bool(dag.catchup), "timetable_kind": "assets" if c is not None else "time"}
    if c is not None:
        row["condition"] = cond(c)
    else:
        last, runs = None, []
        r = TimeRestriction(earliest=dag.start_date, latest=None, catchup=True)
        for _ in range(N_RUNS):
            info = tt.next_dagrun_info(last_automated_data_interval=last, restriction=r)
            if info is None:
                break
            runs.append([info.run_after.isoformat(), info.data_interval.start.isoformat(),
                         info.data_interval.end.isoformat()])
            last = info.data_interval
        row["first_runs"] = runs
    out[dag_id] = row
RESULT = out
"""


def schedules(env_py: str, workspace: Path, dag_ids, env: dict, n_runs: int = 6) -> tuple[dict | None, str]:
    """Per DAG: catchup, and either the asset condition or the first ``n_runs`` scheduled
    (run_after, interval start, interval end) from start_date (catchup restriction)."""
    code = f"DAG_IDS = {sorted(dag_ids)!r}\nN_RUNS = {n_runs}\n" + _SCHEDULE_PROBE
    g.ensure_db(env_py, env)  # 2.x resolves dataset aliases against the DB while parsing
    res, proc = g.probe_json(env_py, code, workspace, env=env)
    return res, proc.tail(20)


def _diff_detail(exp: dict[str, str], have: dict[str, str]) -> str:
    if exp == have:
        return ""
    missing = sorted(set(exp) - set(have))
    extra = sorted(set(have) - set(exp))
    changed = sorted(k for k in set(exp) & set(have) if exp[k] != have[k])
    detail = f"missing={missing} unexpected={extra} changed={changed}"
    for k in changed[:2]:
        detail += f"\n--- {k} expected:\n{exp[k][:700]}\n--- got:\n{have[k][:700]}"
    return detail


def grade_project(case_dir: Path, *, dag_shapes: dict, steps: list, areas: list, env_extra,
                  n_schedule_runs: int = 6) -> None:
    """Standard grader: original replayed in 2.11 vs the agent's project replayed in 3.3.

    ``env_extra(ws) -> dict`` adds deployment settings (plugins folder, custom config)
    for both runs. ``areas = [(check name, (output path prefixes...)), ...]``."""
    args = g.parse_args()
    ws, py = Path(args.workspace), sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    def env_for(env_py, root):
        return g.airflow_env(root, env_py=env_py, extra=env_extra(Path(root)))

    orig_ws = original_workspace(case_dir)
    py2 = g.env_python("2.11")
    exp_sched, log = schedules(py2, orig_ws, dag_shapes, env_for(py2, orig_ws), n_schedule_runs)
    if not exp_sched or any("error" in v for v in exp_sched.values()):
        raise SystemExit(f"case bug: schedule probe failed on the original: {exp_sched}\n{log}")
    shutil.rmtree(orig_ws / "output", ignore_errors=True)
    orig, log = replay(py2, orig_ws, steps, env=env_for(py2, orig_ws), timeout=1500)
    if not runs_ok(orig):
        raise SystemExit(f"case bug: original failed in 2.11: {describe(orig)}\n{log}")
    expected = snapshot(orig_ws)

    imp = g.import_dags(py, ws, env=env_for(py, ws))
    dags = imp["dags"]
    grader.primary(f"all {len(dag_shapes)} DAGs import on Airflow 3.3 (dags/ + plugins/)",
                   imp["ok"] and not imp["import_errors"] and set(dag_shapes) <= set(dags),
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items())
                   or f"missing: {sorted(set(dag_shapes) - set(dags))}")
    def keeps_shape(d, tasks, deps):
        # Original task ids and ordering are kept; added helper tasks are allowed as long
        # as every original dependency still holds (downstream reachable from upstream).
        if d not in dags or not set(tasks) <= set(dags[d]["tasks"]):
            return False
        down: dict[str, set] = {}
        for up, dn in dags[d]["deps"]:
            down.setdefault(up, set()).add(dn)

        def reach(a, b):
            seen, todo = set(), [a]
            while todo:
                n = todo.pop()
                if n == b:
                    return True
                if n not in seen:
                    seen.add(n)
                    todo.extend(down.get(n, ()))
            return False
        return all(reach(up, dn) for up, dn in deps)

    shape_ok = all(keeps_shape(d, t, deps) for d, (t, deps) in dag_shapes.items())
    grader.primary("every DAG keeps its tasks and dependencies (added helper tasks allowed)", shape_ok,
                   "; ".join(f"{d}: tasks={dags[d]['tasks']} deps={dags[d]['deps']}" if d in dags
                             else f"{d}: missing" for d in dag_shapes))

    got_sched, log = schedules(py, ws, dag_shapes, env_for(py, ws), n_schedule_runs)
    diffs = [f"{d}: expected {exp_sched[d]}\n   got {(got_sched or {}).get(d)}"
             for d in sorted(dag_shapes) if (got_sched or {}).get(d) != exp_sched[d]]
    grader.primary("schedules unchanged: same scheduled runs and data intervals, catchup, asset conditions",
                   got_sched is not None and not diffs, "\n".join(diffs) or ("" if got_sched else log))

    shutil.rmtree(ws / "output", ignore_errors=True)
    got, log = replay(py, ws, steps, env=env_for(py, ws), block_orm=True, timeout=1500)
    ok = runs_ok(got)
    grader.primary("every replayed run (scheduled, asset-triggered, CLI-triggered) succeeds on 3.3", ok,
                   describe(got) + ("" if ok else "\n" + log[-2500:]))
    snap = snapshot(ws)
    for name, prefixes in areas:
        exp = {k: v for k, v in expected.items() if k.startswith(prefixes)}
        have = {k: v for k, v in snap.items() if k.startswith(prefixes)}
        grader.primary(name, exp == have, _diff_detail(exp, have))

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)
