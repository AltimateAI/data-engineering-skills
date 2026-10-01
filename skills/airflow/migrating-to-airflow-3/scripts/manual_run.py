#!/usr/bin/env python3
"""Reproduce an Airflow 3 manual trigger that has no logical date, in-process.

`airflow dags test <dag_id>` without a date does NOT reproduce a UI/API/CLI
trigger on Airflow >= 3.0: it sets logical_date to "now". A real manual trigger
leaves logical_date, ds and data_interval_* unset and only dag_run.run_after is
set. This script runs `dag.test(logical_date=None, run_after=...)` so tasks see
exactly that context.

Run it with the Python interpreter of the project's Airflow environment. By
default it runs against a throwaway, freshly migrated sqlite metadata DB (about
5-10 s), because `dag.test(logical_date=None)` clears the state of EVERY task
instance of this DAG in the metadata DB it uses. Provide Variables/Connections
as AIRFLOW_VAR_<NAME> / AIRFLOW_CONN_<ID> env vars. `--use-configured-db` uses
the configured metadata DB instead (stored Variables/Connections visible; this
DAG's task history there is reset; needs `airflow db migrate`).

    python manual_run.py DAG_ID [--run-after 2026-03-04T00:30:00Z]
                         [--dags-folder PATH] [--conf '{"k": "v"}']
                         [--use-configured-db]

stdout is a single JSON object:
  {airflow_version, dag_id, run_id, state, logical_date, run_after,
   task_states: {task_id: state}, failed_tasks: [task_id], errors: [str], exit_code}
Airflow's own logs go to stderr.

Exit codes:
  0  the DAG run succeeded
  1  the DAG file failed to import
  2  the DAG run finished in a non-success state (see failed_tasks and stderr)
  3  usage or environment error (bad arguments, Airflow missing or < 3.0,
     DAG not found, metadata DB not migrated)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

EXIT_OK, EXIT_IMPORT, EXIT_RUN_FAILED, EXIT_USAGE = 0, 1, 2, 3
MAX_ERROR_CHARS = 1500


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # usage errors exit 3, not argparse's 2
        self.print_usage(sys.stderr)
        sys.stderr.write(f"error: {message}\n")
        sys.exit(EXIT_USAGE)


def parse_args(argv):
    p = _Parser(
        description="Run one DAG in-process the way an Airflow 3 manual trigger "
        "without a logical date runs it (logical_date=None, run_after set).",
        epilog="Exit codes: 0 success, 1 import error, 2 run failed, 3 usage/environment error.",
    )
    p.add_argument("dag_id")
    p.add_argument("--run-after", default=None,
                   help="trigger time, ISO 8601 (naive = UTC); default: now")
    p.add_argument("--dags-folder", default=None,
                   help="DAG folder (default: $AIRFLOW__CORE__DAGS_FOLDER, else ./dags)")
    p.add_argument("--conf", default=None, help="dag_run.conf as a JSON object")
    p.add_argument("--use-configured-db", action="store_true",
                   help="use the configured metadata DB instead of a throwaway one "
                   "(resets this DAG's task instance states there)")
    return p.parse_args(argv)


def _trim(text: str) -> str:
    text = str(text).strip()
    return text if len(text) <= MAX_ERROR_CHARS else "..." + text[-MAX_ERROR_CHARS:]


def _installed_major() -> int:
    """Major version of the installed apache-airflow, read without importing it (0 if absent)."""
    from importlib import metadata
    try:
        return int(metadata.version("apache-airflow").split(".")[0])
    except (metadata.PackageNotFoundError, ValueError):
        return 0


def _use_throwaway_db() -> str | None:
    """Points Airflow at a new sqlite DB and migrates it. Returns an error message or None."""
    db_dir = tempfile.mkdtemp(prefix="manual-run-db-")
    url = f"sqlite:///{os.path.join(db_dir, 'airflow.db')}"
    os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = url
    os.environ["AIRFLOW__CORE__SQL_ALCHEMY_CONN"] = url
    try:
        proc = subprocess.run([sys.executable, "-m", "airflow", "db", "migrate"],
                              capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"could not migrate the throwaway metadata DB: {exc}"
    if proc.returncode != 0:
        if "No module named airflow" in proc.stderr:
            return ("apache-airflow is not importable with this Python; "
                    "run the script with the project's Airflow interpreter")
        return f"`airflow db migrate` failed for the throwaway DB: {_trim(proc.stderr)[-600:]}"
    return None


def run(args) -> tuple[dict, int]:
    res: dict = {"dag_id": args.dag_id, "errors": []}
    folder = args.dags_folder or os.environ.get("AIRFLOW__CORE__DAGS_FOLDER") or "dags"
    folder = os.path.abspath(folder)
    if not os.path.exists(folder):
        res["errors"].append(f"DAG folder not found: {folder}")
        return res, EXIT_USAGE
    if args.dags_folder or not os.environ.get("AIRFLOW__CORE__DAGS_FOLDER"):
        # 3.x dag.test() only serializes DAGs that live in the configured DAGs folder.
        os.environ["AIRFLOW__CORE__DAGS_FOLDER"] = folder
    os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    for extra in (os.getcwd(), folder):
        if extra not in sys.path:
            sys.path.insert(0, extra)

    conf = None
    if args.conf:
        try:
            conf = json.loads(args.conf)
        except ValueError as exc:
            res["errors"].append(f"--conf is not valid JSON: {exc}")
            return res, EXIT_USAGE
        if not isinstance(conf, dict):
            res["errors"].append("--conf must be a JSON object")
            return res, EXIT_USAGE

    if not args.use_configured_db and _installed_major() >= 3:
        err = _use_throwaway_db()
        if err:
            res["errors"].append(err)
            return res, EXIT_USAGE

    try:
        import airflow
    except ImportError:
        res["errors"].append("apache-airflow is not importable with this Python; "
                             "run the script with the project's Airflow interpreter")
        return res, EXIT_USAGE
    res["airflow_version"] = airflow.__version__
    try:
        major = int(airflow.__version__.split(".")[0])
    except ValueError:
        major = None
    if major is None or major < 3:
        res["errors"].append(
            "Airflow < 3.0: manual runs always get a logical date (default: now), so "
            "`airflow dags test <dag_id> <date>` already reproduces them")
        return res, EXIT_USAGE

    import pendulum
    try:
        from airflow.dag_processing.dagbag import DagBag  # Airflow >= 3.2
    except ImportError:
        from airflow.models.dagbag import DagBag  # Airflow 3.0 / 3.1

    run_after = pendulum.now("UTC")
    if args.run_after:
        try:
            run_after = pendulum.parse(args.run_after, tz="UTC")
        except Exception as exc:  # noqa: BLE001
            res["errors"].append(f"--run-after is not an ISO datetime: {exc}")
            return res, EXIT_USAGE

    bag = DagBag(dag_folder=folder)
    if bag.import_errors:
        res["import_errors"] = [{"file": f, "error": _trim(e)} for f, e in bag.import_errors.items()]
    dag = bag.dags.get(args.dag_id)
    if dag is None:
        if bag.import_errors:
            return res, EXIT_IMPORT
        res["errors"].append(f"DAG {args.dag_id!r} not found in {folder}; "
                             f"found: {sorted(bag.dags)[:20]}")
        return res, EXIT_USAGE

    kwargs = {"logical_date": None, "run_after": run_after}
    if conf is not None:
        kwargs["run_conf"] = conf
    try:
        dr = dag.test(**kwargs)
    except Exception as exc:  # noqa: BLE001
        first = (str(exc).strip().splitlines() or [""])[0][:400]
        msg = f"{type(exc).__name__}: {first}"
        low = str(exc).lower()
        if "migrat" in low or "no such table" in low or "does not exist" in low:
            msg = ("metadata DB is not initialised for AIRFLOW_HOME="
                   f"{os.environ.get('AIRFLOW_HOME', '~/airflow')}: run `airflow db migrate` "
                   f"first ({msg[:200]})")
        res["errors"].append(msg)
        return res, EXIT_USAGE

    res.update({
        "run_id": getattr(dr, "run_id", None),
        "state": str(getattr(dr, "state", None)),
        "logical_date": str(dr.logical_date) if getattr(dr, "logical_date", None) else None,
        "run_after": str(getattr(dr, "run_after", run_after)),
    })
    states = {}
    try:
        for ti in dr.get_task_instances():
            states[ti.task_id if ti.map_index < 0 else f"{ti.task_id}[{ti.map_index}]"] = str(ti.state)
    except Exception as exc:  # noqa: BLE001
        res["errors"].append(f"could not read task states: {type(exc).__name__}: {exc}")
    res["task_states"] = dict(sorted(states.items())[:200])
    res["failed_tasks"] = sorted(k for k, v in states.items()
                                 if v in ("failed", "upstream_failed", "TaskInstanceState.FAILED",
                                          "TaskInstanceState.UPSTREAM_FAILED"))[:200]
    ok = res["state"] in ("success", "DagRunState.SUCCESS")
    return res, EXIT_OK if ok else EXIT_RUN_FAILED


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    # Airflow and DAG code print/log to stdout; keep stdout for the JSON result only.
    sys.stdout.flush()
    real_fd = os.dup(1)
    os.dup2(2, 1)
    try:
        try:
            res, code = run(args)
        except Exception as exc:  # noqa: BLE001
            res, code = {"dag_id": args.dag_id,
                         "errors": [_trim(f"internal error: {type(exc).__name__}: {exc}")]}, EXIT_USAGE
        res["exit_code"] = code
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(real_fd, 1)
        os.close(real_fd)
    sys.stdout.write(json.dumps(res, indent=2, default=str) + "\n")
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
