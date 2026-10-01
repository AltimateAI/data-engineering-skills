#!/usr/bin/env python3
"""Run several consecutive runs of one DAG against ONE throwaway metadata DB.

One `airflow dags test` proves a single run. A DAG that carries state from run
to run (a watermark in XCom read with include_prior_dates, a Variable it
updates, a file the previous run wrote, depends_on_past) breaks only on the
second or third run, or after a manual trigger lands between two scheduled
runs. This script replays that sequence:

  * N scheduled runs taken from the DAG's own timetable (the same preview the
    scheduler computes), each with the scheduler's logical_date,
    data_interval and run_after, and run_type "scheduled";
  * optional manual runs (--manual RUN_AFTER): on Airflow >= 3 these have no
    logical date, exactly like a UI/API/CLI trigger with an empty date field;
    on 2.x a manual run gets logical_date = the trigger time;
  * optional reruns (--rerun K) of the K-th scheduled run, executed last, to
    check that re-processing a period gives the same result.

All runs share one metadata DB, so XComs, Variables and task history from
earlier runs are visible to later ones. Files written by tasks persist as
usual. Runs execute in run_after order (reruns at the end), each in its own
process (as on real workers, module-level state does not survive between
runs); a run still going after --run-timeout seconds is killed and the
replay stops.

Run it with the Python interpreter of the project's Airflow environment:

    python replay_runs.py DAG_ID [--runs 3] [--from 2026-03-02]
                          [--manual 2026-03-04T09:30:00Z ...] [--rerun 1 ...]
                          [--var KEY=VALUE ...] [--conf '{"k": "v"}']
                          [--dags-folder PATH] [--show-xcom]
                          [--run-timeout 600] [--use-configured-db]

--from picks the first scheduled run (default: the DAG's start_date).
--var seeds a Variable in the metadata DB (unlike AIRFLOW_VAR_* env vars,
which shadow the DB, a seeded Variable can be updated by Variable.set and
the next run reads the new value). Connections: AIRFLOW_CONN_<ID> env vars.

stdout is JSON Lines: one object per run, in execution order,
  {index, kind, run_id, run_type, logical_date, run_after,
   data_interval_start, data_interval_end, state, task_states,
   failed_tasks, duration_s, errors[, xcom]}
then one summary line {"summary": {...}}. Airflow's own logs go to stderr.

Exit codes:
  0  every run succeeded
  1  the DAG file failed to import
  2  at least one run did not succeed (see failed_tasks and stderr)
  3  usage or environment error (bad arguments, Airflow missing, DAG not
     found, nothing to run: no time-based schedule or --runs 0, and no --manual)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

EXIT_OK, EXIT_IMPORT, EXIT_RUN_FAILED, EXIT_USAGE = 0, 1, 2, 3
MAX_ERROR_CHARS = 1500
MAX_RUNS = 50
MAX_XCOM_CHARS = 300
SUCCESS = ("success", "DagRunState.SUCCESS")
FAILED_TI = ("failed", "upstream_failed", "TaskInstanceState.FAILED",
             "TaskInstanceState.UPSTREAM_FAILED")


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # usage errors exit 3, not argparse's 2
        self.print_usage(sys.stderr)
        sys.stderr.write(f"error: {message}\n")
        sys.exit(EXIT_USAGE)


def parse_args(argv):
    p = _Parser(
        description="Replay consecutive scheduled (and optional manual) runs of one DAG "
        "in a single throwaway metadata DB, so state carried between runs is exercised.",
        epilog="Exit codes: 0 all runs succeeded, 1 import error, 2 a run failed, "
        "3 usage/environment error.",
    )
    p.add_argument("dag_id")
    p.add_argument("--runs", type=int, default=3,
                   help="consecutive scheduled runs from the timetable (default 3; 0 = none)")
    p.add_argument("--from", dest="start_from", default=None, metavar="DATE",
                   help="first scheduled run at or after this date (default: start_date)")
    p.add_argument("--manual", action="append", default=[], metavar="RUN_AFTER",
                   help="add a manual run triggered at this time (ISO 8601, naive = UTC); "
                   "repeatable")
    p.add_argument("--rerun", action="append", type=int, default=[], metavar="K",
                   help="re-run the K-th scheduled run (1-based) after all other runs; repeatable")
    p.add_argument("--var", action="append", default=[], metavar="KEY=VALUE",
                   help="seed a Variable in the metadata DB before the first run; repeatable")
    p.add_argument("--conf", default=None, help="dag_run.conf (JSON object) for every run")
    p.add_argument("--dags-folder", default=None,
                   help="DAG folder (default: $AIRFLOW__CORE__DAGS_FOLDER, else ./dags)")
    p.add_argument("--show-xcom", action="store_true",
                   help="include each run's XComs (values truncated) in its JSON line")
    p.add_argument("--run-timeout", type=int, default=600,
                   help="seconds before one run counts as hung (default 600)")
    p.add_argument("--use-configured-db", action="store_true",
                   help="use the configured metadata DB instead of a throwaway one "
                   "(this DAG's runs for the replayed dates are replaced there)")
    p.add_argument("--_child", default=None, help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _trim(text, limit: int = MAX_ERROR_CHARS) -> str:
    text = str(text).strip()
    return text if len(text) <= limit else "..." + text[-limit:]


def _iso(value):
    return value.isoformat() if value is not None else None


def _use_throwaway_db() -> tuple[str | None, str | None]:
    """Points Airflow at a new sqlite DB and migrates it. Returns (db_path, error)."""
    db_dir = tempfile.mkdtemp(prefix="replay-runs-db-")
    path = os.path.join(db_dir, "airflow.db")
    url = f"sqlite:///{path}"
    os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = url
    os.environ["AIRFLOW__CORE__SQL_ALCHEMY_CONN"] = url
    try:
        proc = subprocess.run([sys.executable, "-m", "airflow", "db", "migrate"],
                              capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"could not migrate the throwaway metadata DB: {exc}"
    if proc.returncode != 0:
        if "No module named airflow" in proc.stderr:
            return None, ("apache-airflow is not importable with this Python; "
                          "run the script with the project's Airflow interpreter")
        return None, f"`airflow db migrate` failed for the throwaway DB: {_trim(proc.stderr)[-600:]}"
    return path, None


def _core_timetable(dag):
    """Scheduler-side timetable (3.x SDK timetables lack next_dagrun_info)."""
    for mod in ("airflow.serialization.encoders", "airflow.serialization.serialized_objects"):
        try:
            coerce = getattr(__import__(mod, fromlist=["coerce_to_core_timetable"]),
                             "coerce_to_core_timetable")
        except (ImportError, AttributeError):
            continue
        try:
            return coerce(dag.timetable)
        except Exception:  # noqa: BLE001 - fall back to whatever the DAG carries
            break
    return dag.timetable


def _aware(value, tz):
    import pendulum

    if isinstance(value, str):
        return pendulum.parse(value, tz=tz)
    if value.tzinfo is None:
        return pendulum.instance(value, tz=tz)
    return pendulum.instance(value)


def plan_scheduled(dag, n: int, start_from: str | None) -> tuple[list[dict], str | None]:
    """The first ``n`` scheduled runs at/after ``start_from`` (or start_date), catchup-style."""
    if n <= 0:
        return [], None
    from airflow.timetables.base import TimeRestriction

    tt = _core_timetable(dag)
    if not hasattr(tt, "next_dagrun_info"):
        return [], "the DAG's timetable cannot be previewed (no next_dagrun_info)"
    tz = getattr(dag, "timezone", None) or "UTC"
    start_date = getattr(dag, "start_date", None)
    earliest = _aware(start_from, tz) if start_from else None
    if start_date is not None and (earliest is None or _aware(start_date, tz) > earliest):
        earliest = _aware(start_date, tz)
    if earliest is None:
        return [], "the DAG has no start_date: pass --from"
    end_date = getattr(dag, "end_date", None)
    latest = _aware(end_date, tz) if end_date is not None else None
    restriction = TimeRestriction(earliest=earliest, latest=latest, catchup=True)
    plan, last = [], None
    for _ in range(n):
        info = tt.next_dagrun_info(last_automated_data_interval=last, restriction=restriction)
        if info is None or info.data_interval is None:
            break
        di = info.data_interval
        plan.append({"kind": "scheduled", "logical_date": getattr(info, "logical_date", di.start),
                     "run_after": info.run_after, "data_interval": (di.start, di.end)})
        last = di
    if not plan:
        return [], ("the timetable produced no scheduled runs (schedule=None, an asset "
                    "schedule, or end_date before --from): use --manual")
    return plan, None


def _patch_run_creation(major: int, planned: dict):
    """Make dag.test() create the run the scheduler would create for ``planned``.

    dag.test() always creates a MANUAL run whose data_interval is inferred from the
    logical date, which differs from a scheduled run under interval timetables.
    Returns an undo callable, or None when the internals are not as expected.
    """
    from airflow.utils.types import DagRunType

    if major >= 3:
        import airflow.models.dagrun as mod
        name = "get_or_create_dagrun"
    else:
        import airflow.models.dag as mod
        name = "_get_or_create_dagrun"
        try:  # 2.x: deleting a run (rerun) needs the ab_user table mapped
            import airflow.providers.fab.auth_manager.models  # noqa: F401
        except ImportError:
            pass
    orig = getattr(mod, name, None)
    if orig is None:
        return None
    from airflow.models.dagrun import DagRun

    def scheduled_run(*args, **kwargs):
        if args:  # unexpected calling convention: do not guess
            return orig(*args, **kwargs)
        kwargs["data_interval"] = planned["data_interval"]
        if major >= 3:
            kwargs["run_after"] = planned["run_after"]
            kwargs["run_id"] = DagRun.generate_run_id(
                run_type=DagRunType.SCHEDULED, logical_date=planned["logical_date"],
                run_after=planned["run_after"])
        else:
            kwargs["run_id"] = DagRun.generate_run_id(DagRunType.SCHEDULED,
                                                      planned["logical_date"])
        target = kwargs.get("dag")
        create = getattr(target, "create_dagrun", None)
        if create is None:
            return orig(**kwargs)

        def create_scheduled(*c_args, **c_kwargs):
            c_kwargs["run_type"] = DagRunType.SCHEDULED
            return create(*c_args, **c_kwargs)

        # orig() deletes any earlier run for this logical date, then creates a MANUAL run;
        # only the run type is swapped, on this DAG object, for this one call.
        object.__setattr__(target, "create_dagrun", create_scheduled)
        try:
            return orig(**kwargs)
        finally:
            object.__delattr__(target, "create_dagrun")

    setattr(mod, name, scheduled_run)
    return lambda: setattr(mod, name, orig)


def _patch_manual_creation(major: int):
    """Make dag.test() create the run a real manual trigger would create.

    3.x: dag.test() deletes any earlier run with the same logical date before creating
    its own, and for a manual run that is every earlier manual run (logical_date IS NULL);
    a replay must keep them. 2.x: a real trigger sets external_trigger=True, which the
    context uses (prev_execution_date / next_execution_date). Returns an undo callable,
    or None when the internals are not as expected.
    """
    from airflow.utils.state import DagRunState
    from airflow.utils.types import DagRunType

    if major >= 3:
        import airflow.models.dagrun as mod
        name = "get_or_create_dagrun"
    else:
        import airflow.models.dag as mod
        name = "_get_or_create_dagrun"
    orig = getattr(mod, name, None)
    if orig is None:
        return None

    def manual_run(*args, **kwargs):
        target = kwargs.get("dag")
        create = getattr(target, "create_dagrun", None)
        if args or create is None:  # unexpected calling convention: do not guess
            return orig(*args, **kwargs)
        if major < 3:
            def create_external(*c_args, **c_kwargs):
                c_kwargs["external_trigger"] = True
                return create(*c_args, **c_kwargs)

            object.__setattr__(target, "create_dagrun", create_external)
            try:
                return orig(**kwargs)
            finally:
                object.__delattr__(target, "create_dagrun")
        if kwargs.get("logical_date") is not None:
            return orig(**kwargs)
        # Same call as get_or_create_dagrun() makes, without deleting earlier manual runs.
        return create(run_id=kwargs["run_id"], logical_date=None,
                      data_interval=kwargs.get("data_interval"), run_after=kwargs["run_after"],
                      conf=kwargs.get("conf"), run_type=DagRunType.MANUAL,
                      state=DagRunState.RUNNING, triggered_by=kwargs.get("triggered_by"),
                      triggering_user_name=kwargs.get("triggering_user_name"),
                      start_date=kwargs.get("start_date"), session=kwargs["session"])

    setattr(mod, name, manual_run)
    return lambda: setattr(mod, name, orig)


def _skip_clear_for_manual_runs():
    """dag.test(logical_date=None) clears EVERY task instance of the DAG; a replay must not."""
    try:
        from airflow.serialization.definitions.dag import SerializedDAG
    except ImportError:
        return lambda: None
    orig = SerializedDAG.__dict__.get("clear_dags")
    if orig is None:
        return lambda: None
    SerializedDAG.clear_dags = classmethod(lambda cls, *a, **k: 0)
    return lambda: setattr(SerializedDAG, "clear_dags", orig)


def _seed_variables(pairs: list[str]) -> str | None:
    from airflow.models import Variable

    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            return f"--var expects KEY=VALUE, got {pair!r}"
        Variable.set(key, value)
    return None


def _xcoms(dag_id: str, run_id: str) -> dict:
    from airflow.utils.session import create_session

    try:
        from airflow.models.xcom import XComModel as model  # Airflow >= 3.0
    except ImportError:
        from airflow.models.xcom import BaseXCom as model
    out = {}
    with create_session() as session:
        rows = session.query(model).filter(model.dag_id == dag_id, model.run_id == run_id).all()
        for row in rows:
            value = row.value
            if hasattr(model, "deserialize_value"):
                try:
                    value = model.deserialize_value(row)
                except Exception:  # noqa: BLE001 - show the stored form instead
                    pass
            task = row.task_id if getattr(row, "map_index", -1) < 0 else f"{row.task_id}[{row.map_index}]"
            out[f"{task}.{row.key}"] = _trim(json.dumps(value, default=str), MAX_XCOM_CHARS)
    return dict(sorted(out.items()))


def _execute(dag, major: int, planned: dict, conf) -> dict:
    rec = {"kind": planned["kind"], "errors": []}
    undo = []
    kwargs: dict = {}
    if conf is not None:
        kwargs["run_conf"] = conf
    if planned["kind"] == "manual":
        restore = _patch_manual_creation(major)
        if restore is None:
            rec["errors"].append("could not patch manual-run creation; earlier manual runs "
                                 "may have been replaced (3.x) or external_trigger is False (2.x)")
        else:
            undo.append(restore)
        if major >= 3:
            kwargs.update(logical_date=None, run_after=planned["run_after"])
            undo.append(_skip_clear_for_manual_runs())
        else:
            kwargs["execution_date"] = planned["run_after"]
    else:
        restore = _patch_run_creation(major, planned)
        if restore is None:
            rec["errors"].append("could not pin the scheduled data interval; this run used "
                                 "dag.test()'s inferred manual interval")
        else:
            undo.append(restore)
        if major >= 3:
            kwargs.update(logical_date=planned["logical_date"], run_after=planned["run_after"])
        else:
            kwargs["execution_date"] = planned["logical_date"]

    started = time.monotonic()
    dr = None
    try:
        dr = dag.test(**kwargs)
    except Exception as exc:  # noqa: BLE001
        first = (str(exc).strip().splitlines() or [""])[0][:400]
        rec["errors"].append(f"{type(exc).__name__}: {first}")
        rec["state"] = "error"
    finally:
        for fn in reversed(undo):
            fn()
    rec["duration_s"] = round(time.monotonic() - started, 2)
    if dr is None:
        rec.update(run_id=None, run_type=None, logical_date=_iso(planned.get("logical_date")),
                   run_after=_iso(planned.get("run_after")), task_states={}, failed_tasks=[])
        return rec
    rec.update({
        "run_id": dr.run_id,
        "run_type": str(getattr(dr.run_type, "value", dr.run_type)),
        "logical_date": _iso(getattr(dr, "logical_date", None) if major >= 3
                             else getattr(dr, "execution_date", None)),
        "run_after": _iso(getattr(dr, "run_after", None) or planned.get("run_after")),
        "data_interval_start": _iso(getattr(dr, "data_interval_start", None)),
        "data_interval_end": _iso(getattr(dr, "data_interval_end", None)),
        "state": str(getattr(dr.state, "value", dr.state)),
    })
    states = {}
    try:
        for ti in dr.get_task_instances():
            key = ti.task_id if ti.map_index < 0 else f"{ti.task_id}[{ti.map_index}]"
            states[key] = str(getattr(ti.state, "value", ti.state))
    except Exception as exc:  # noqa: BLE001
        rec["errors"].append(f"could not read task states: {type(exc).__name__}: {exc}")
    rec["task_states"] = dict(sorted(states.items())[:200])
    rec["failed_tasks"] = sorted(k for k, v in states.items() if v in FAILED_TI)[:200]
    return rec


def _emit(obj: dict, real_stdout_fd: int) -> None:
    line = (json.dumps(obj, default=str) + "\n").encode()
    sys.stdout.flush()
    os.write(real_stdout_fd, line)


def _prepare_paths(folder: str) -> None:
    os.environ["AIRFLOW__CORE__DAGS_FOLDER"] = folder
    os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    for extra in (os.getcwd(), folder):
        if extra not in sys.path:
            sys.path.insert(0, extra)


def _load_bag(folder: str, major: int):
    try:
        from airflow.dag_processing.dagbag import DagBag  # Airflow >= 3.2
    except ImportError:
        from airflow.models.dagbag import DagBag
    if major >= 3:
        return DagBag(dag_folder=folder)  # examples off via AIRFLOW__CORE__LOAD_EXAMPLES
    return DagBag(dag_folder=folder, include_examples=False)


def _airflow_major() -> int:
    import airflow

    try:
        return int(airflow.__version__.split(".")[0])
    except ValueError:
        return 3


def _exit_with_parent() -> None:
    """Kill this run (its own process group) when the replay process that started it dies.

    The run is a session leader so a hung run can be killed with its task subprocesses;
    without this watchdog, killing the replay (a caller's timeout, Ctrl-C) would leave it
    running against the same metadata DB and outputs.
    """
    import threading

    parent = os.getppid()

    def watch():
        while os.getppid() == parent:
            time.sleep(1)
        os.killpg(os.getpgrp(), signal.SIGKILL)

    threading.Thread(target=watch, daemon=True).start()


def child_main(dag_id: str, spec_json: str, real_stdout_fd: int) -> int:
    """One run, in its own process, so a hung run can be killed and module state is fresh."""
    import pendulum

    spec = json.loads(spec_json)
    _exit_with_parent()
    _prepare_paths(spec["folder"])
    major = _airflow_major()
    planned = dict(spec["planned"])
    for key in ("logical_date", "run_after"):
        if planned.get(key):
            planned[key] = pendulum.parse(planned[key])
    if planned.get("data_interval"):
        planned["data_interval"] = tuple(pendulum.parse(v) for v in planned["data_interval"])
    dag = _load_bag(spec["folder"], major).dags.get(dag_id)
    if dag is None:
        rec = {"kind": planned["kind"], "state": "error", "errors": [
            f"DAG {dag_id!r} did not load in the run's process (import error?)"]}
    else:
        rec = _execute(dag, major, planned, spec.get("conf"))
        if spec.get("show_xcom") and rec.get("run_id"):
            try:
                rec["xcom"] = _xcoms(dag_id, rec["run_id"])
            except Exception as exc:  # noqa: BLE001
                rec["errors"].append(f"could not read XComs: {type(exc).__name__}: {exc}")
    _emit(rec, real_stdout_fd)
    return 0


def _spec_planned(planned: dict) -> dict:
    out = {"kind": planned["kind"], "logical_date": _iso(planned.get("logical_date")),
           "run_after": _iso(planned.get("run_after"))}
    if planned.get("data_interval"):
        out["data_interval"] = [_iso(v) for v in planned["data_interval"]]
    return out


def _run_in_child(dag_id: str, spec: dict, timeout: int) -> dict:
    cmd = [sys.executable, os.path.abspath(__file__), dag_id, "--_child", json.dumps(spec)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=None, text=True,
                            start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        proc.communicate()
        return {"state": "timeout", "errors": [
            f"run did not finish within {timeout}s and was killed: a task waits forever (a "
            "sensor whose condition never comes true, or depends_on_past/wait_for_downstream "
            "after a failed earlier run)"], "duration_s": float(timeout)}
    for line in reversed((out or "").splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {"state": "error", "errors": [f"run process exited {proc.returncode} without a "
                                         "result (see stderr)"]}


def run(args, real_stdout_fd: int) -> tuple[dict, int]:
    summary: dict = {"dag_id": args.dag_id, "errors": []}
    if args.runs < 0 or args.runs > MAX_RUNS:
        summary["errors"].append(f"--runs must be between 0 and {MAX_RUNS}")
        return summary, EXIT_USAGE
    if args.runs == 0 and not args.manual:
        summary["errors"].append("nothing to run: --runs 0 needs at least one --manual")
        return summary, EXIT_USAGE
    if args.run_timeout <= 0:
        summary["errors"].append("--run-timeout must be a positive number of seconds")
        return summary, EXIT_USAGE
    folder = os.path.abspath(args.dags_folder or os.environ.get("AIRFLOW__CORE__DAGS_FOLDER")
                             or "dags")
    if not os.path.exists(folder):
        summary["errors"].append(f"DAG folder not found: {folder}")
        return summary, EXIT_USAGE
    # 3.x dag.test() only serializes DAGs that live in the configured DAGs folder.
    _prepare_paths(folder)

    conf = None
    if args.conf:
        try:
            conf = json.loads(args.conf)
        except ValueError as exc:
            summary["errors"].append(f"--conf is not valid JSON: {exc}")
            return summary, EXIT_USAGE
        if not isinstance(conf, dict):
            summary["errors"].append("--conf must be a JSON object")
            return summary, EXIT_USAGE

    if not args.use_configured_db:
        db_path, err = _use_throwaway_db()
        if err:
            summary["errors"].append(err)
            return summary, EXIT_USAGE
        summary["metadata_db"] = db_path

    try:
        import airflow
        import pendulum
    except ImportError:
        summary["errors"].append("apache-airflow is not importable with this Python; "
                                 "run the script with the project's Airflow interpreter")
        return summary, EXIT_USAGE
    summary["airflow_version"] = airflow.__version__
    major = _airflow_major()

    manual = []
    for value in args.manual:
        try:
            manual.append({"kind": "manual", "run_after": pendulum.parse(value, tz="UTC")})
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"--manual {value!r} is not an ISO datetime: {exc}")
            return summary, EXIT_USAGE

    bag = _load_bag(folder, major)
    if bag.import_errors:
        summary["import_errors"] = [{"file": f, "error": _trim(e)}
                                    for f, e in bag.import_errors.items()]
    dag = bag.dags.get(args.dag_id)
    if dag is None:
        if bag.import_errors:
            return summary, EXIT_IMPORT
        summary["errors"].append(f"DAG {args.dag_id!r} not found in {folder}; "
                                 f"found: {sorted(bag.dags)[:20]}")
        return summary, EXIT_USAGE

    scheduled, err = plan_scheduled(dag, args.runs, args.start_from)
    if err and not manual:
        summary["errors"].append(err)
        return summary, EXIT_USAGE
    if err:
        summary["errors"].append(err)
    for k in args.rerun:
        if not 1 <= k <= len(scheduled):
            summary["errors"].append(f"--rerun {k}: only {len(scheduled)} scheduled runs planned")
            return summary, EXIT_USAGE

    err = _seed_variables(args.var)
    if err:
        summary["errors"].append(err)
        return summary, EXIT_USAGE

    order = sorted(scheduled + manual, key=lambda p: p["run_after"])
    order += [dict(scheduled[k - 1], kind="rerun", rerun_of=k) for k in args.rerun]
    records = []
    for index, planned in enumerate(order, start=1):
        spec = {"folder": folder, "planned": _spec_planned(planned), "conf": conf,
                "show_xcom": args.show_xcom}
        rec = {"index": index, "kind": planned["kind"],
               **_run_in_child(args.dag_id, spec, args.run_timeout)}
        rec["kind"] = planned["kind"]
        if planned.get("rerun_of"):
            rec["rerun_of"] = planned["rerun_of"]
        rec.setdefault("logical_date", _iso(planned.get("logical_date")))
        rec.setdefault("run_after", _iso(planned.get("run_after")))
        records.append(rec)
        _emit(rec, real_stdout_fd)
        if rec.get("state") == "timeout":
            summary["errors"].append("stopped after a hung run; later runs were not executed")
            break
    failed = [r["index"] for r in records if r.get("state") not in SUCCESS]
    summary.update({"runs": len(records), "planned": len(order),
                    "succeeded": len(records) - len(failed), "failed_runs": failed})
    return summary, EXIT_OK if not failed and len(records) == len(order) else EXIT_RUN_FAILED


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    # Airflow and DAG code print/log to stdout; keep stdout for the JSON lines only.
    sys.stdout.flush()
    real_fd = os.dup(1)
    os.dup2(2, 1)
    if args._child is not None:
        try:
            return child_main(args.dag_id, args._child, real_fd)
        finally:
            os.dup2(real_fd, 1)
            os.close(real_fd)
    try:
        try:
            summary, code = run(args, real_fd)
        except Exception as exc:  # noqa: BLE001
            summary, code = {"dag_id": args.dag_id, "errors": [
                _trim(f"internal error: {type(exc).__name__}: {exc}")]}, EXIT_USAGE
        summary["exit_code"] = code
        sys.stdout.flush()
        sys.stderr.flush()
        _emit({"summary": summary}, real_fd)
    finally:
        os.dup2(real_fd, 1)
        os.close(real_fd)
    return code


if __name__ == "__main__":
    sys.exit(main())
