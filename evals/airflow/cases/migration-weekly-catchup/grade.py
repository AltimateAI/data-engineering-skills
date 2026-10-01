"""Grader for migration-weekly-catchup.

The fixture is an Airflow 2.11 marketing project. ``weekly_campaign_report``
relies on three Airflow 2 behaviours that change silently in Airflow 3:

- no ``catchup`` argument: Airflow 2 defaulted to ``catchup=True`` and the team
  re-runs whole seasons by moving ``start_date`` back (README); Airflow 3
  defaults to ``catchup=False``;
- a bare cron string with ``{{ ds }}``/``{{ next_ds }}``: the Monday 06:00 run
  reports on the PREVIOUS week; under Airflow 3's CronTriggerTimetable it would
  report on the week that has just started (and ``next_ds`` no longer exists);
- ``sla``/``sla_miss_callback``: accepted by Airflow 3 but no-ops, so the
  "report late" page to on-call silently disappears; Deadline Alerts replace it.

Behaviour is compared with the ORIGINAL project replayed in the 2.11 env.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR))
import migsim  # noqa: E402

g = migsim.g
DAG_ID = "weekly_campaign_report"
OTHER_DAG = "campaign_sync"
RUN_AFTERS = ["2026-03-09T06:00:00+00:00", "2026-03-16T06:00:00+00:00"]
EXPECTED_TASKS = {"summarize_week", "publish_manifest"}
EXPECTED_DEPS = [["summarize_week", "publish_manifest"]]
# Season backfill: every run the scheduler creates from start_date up to this point.
CATCHUP_CUTOFF = "2026-03-16T06:00:00+00:00"
# SLA: the Monday 06:00 run must be finished by 09:00 UTC.
DEADLINE_RUN_AFTER = "2026-03-09T06:00:00+00:00"
DEADLINE_EXPECTED = "2026-03-09T09:00:00+00:00"
DEADLINE_TOLERANCE_S = 300

CATCHUP_PROBE = f"""
import pendulum
from airflow.timetables.base import TimeRestriction
dag = get_dag({DAG_ID!r})
tt = core_timetable(dag)
cutoff = pendulum.parse({CATCHUP_CUTOFF!r})
restriction = TimeRestriction(earliest=dag.start_date, latest=None, catchup=bool(dag.catchup))
runs, last = [], None
for _ in range(60):
    info = tt.next_dagrun_info(last_automated_data_interval=last, restriction=restriction)
    if info is None or info.run_after > cutoff:
        break
    runs.append(info.run_after.isoformat())
    last = info.data_interval
RESULT = {{"catchup": bool(dag.catchup), "timetable": type(tt).__name__, "run_afters": runs}}
"""

DEADLINE_PROBE = f"""
import pendulum
from airflow.timetables.base import TimeRestriction
dag = get_dag({DAG_ID!r})
tt = core_timetable(dag)
target = pendulum.parse({DEADLINE_RUN_AFTER!r})
info, last = None, None
restriction = TimeRestriction(earliest=dag.start_date, latest=None, catchup=True)
for _ in range(5000):
    nxt = tt.next_dagrun_info(last_automated_data_interval=last, restriction=restriction)
    if nxt is None or nxt.run_after > target:
        break
    if nxt.run_after == target:
        info = nxt
        break
    last = nxt.data_interval
alerts = []
for alert in (getattr(dag, "deadline", None) or []):
    ref = type(alert.reference).__name__
    row = {{"reference": ref, "interval": str(alert.interval),
            "callback": getattr(getattr(alert, "callback", None), "path", None)}}
    base = None
    if ref == "DagRunQueuedAtDeadline":
        base = target  # a scheduled run is queued when it becomes due
    elif ref == "DagRunLogicalDateDeadline" and info is not None:
        base = info.logical_date
    elif ref == "FixedDatetimeDeadline":
        row["due"] = None
    if base is not None and hasattr(alert.interval, "total_seconds"):
        row["due"] = (base + alert.interval).isoformat()
    alerts.append(row)
RESULT = {{"found_run": info is not None, "alerts": alerts}}
"""


def snapshot_reports(ws: Path) -> dict[str, str]:
    out = {}
    for path, text in migsim.snapshot(ws).items():
        if not (path.startswith("weekly/") or path.startswith("manifests/")):
            continue
        if path.endswith(".json"):
            try:
                text = json.dumps(json.loads(text), sort_keys=True)
            except ValueError:
                text = f"<invalid json> {text[:200]}"
        out[path] = text
    return out


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    # Ground truth: the untouched Airflow 2 project under the 2.11 scheduler logic.
    py2 = g.env_python("2.11")
    orig_ws, orig, orig_log = migsim.run_original(CASE_DIR, DAG_ID, RUN_AFTERS)
    if not migsim.runs_ok(orig):
        raise SystemExit(f"case bug: original project failed in 2.11: {migsim.describe(orig)}\n{orig_log}")
    expected = snapshot_reports(orig_ws)
    orig_catchup, proc = g.probe_json(py2, CATCHUP_PROBE, orig_ws, env=g.airflow_env(orig_ws, env_py=py2))
    if not orig_catchup or len(orig_catchup["run_afters"]) < 5:
        raise SystemExit(f"case bug: catchup probe on the original failed: {orig_catchup} {proc.tail(30)}")

    imp = g.import_dags(py, ws)
    dag = imp["dags"].get(DAG_ID)
    grader.primary("DAGs import cleanly on Airflow 3.3",
                   imp["ok"] and not imp["import_errors"] and {DAG_ID, OTHER_DAG} <= set(imp["dags"]),
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items())
                   or f"dags: {sorted(imp['dags'])}")
    grader.primary("weekly_campaign_report keeps its tasks and dependency",
                   dag is not None and set(dag["tasks"]) == EXPECTED_TASKS and dag["deps"] == EXPECTED_DEPS,
                   f"tasks={dag and dag['tasks']} deps={dag and dag['deps']}")

    if dag is None:
        grader.primary("dags test succeeds (weekly_campaign_report, campaign_sync)", False, "DAG missing")
    else:
        shutil.rmtree(ws / "output", ignore_errors=True)
        cli, cli_log = migsim.simulate(py, ws, DAG_ID, [migsim.manual("2026-03-09")])
        other, other_log = migsim.simulate(py, ws, OTHER_DAG, [migsim.manual("2026-03-09")])
        ok = migsim.runs_ok(cli) and migsim.runs_ok(other)
        grader.primary("dags test succeeds (weekly_campaign_report, campaign_sync)", ok,
                       "" if ok else f"{DAG_ID}: {migsim.describe(cli)}\n{OTHER_DAG}: {migsim.describe(other)}\n"
                       f"{(cli_log if not migsim.runs_ok(cli) else other_log)[-2500:]}")

        shutil.rmtree(ws / "output", ignore_errors=True)
        sim, sim_log = migsim.simulate(py, ws, DAG_ID, RUN_AFTERS, block_orm=True)
        grader.primary("scheduled Monday 06:00 runs succeed on 3.3", migsim.runs_ok(sim),
                       migsim.describe(sim) + ("" if migsim.runs_ok(sim) else "\n" + sim_log[-2500:]))
        got = snapshot_reports(ws)
        grader.primary("Monday runs report on the previous week, same output as 2.11", got == expected,
                       f"expected {expected}\n got {got}")

        got_catchup, proc = g.probe_json(py, CATCHUP_PROBE, ws, env=g.airflow_env(ws, env_py=py))
        grader.primary(
            "season backfill: scheduler creates the same weekly runs from start_date as 2.11",
            bool(got_catchup) and got_catchup["run_afters"] == orig_catchup["run_afters"],
            f"expected run_afters {orig_catchup['run_afters']}\n got {got_catchup or proc.tail(20)}")

        dl, proc = g.probe_json(py, DEADLINE_PROBE, ws, env=g.airflow_env(ws, env_py=py))
        import pendulum  # noqa: PLC0415 (grade.py runs in the Airflow env)

        want = pendulum.parse(DEADLINE_EXPECTED)
        hits = [a for a in (dl or {}).get("alerts", [])
                if a.get("due") and a.get("callback")
                and abs((pendulum.parse(a["due"]) - want).total_seconds()) <= DEADLINE_TOLERANCE_S]
        grader.primary("late-report alert still fires at 09:00 UTC for the Monday run (Deadline Alert)",
                       bool(hits), f"alerts={dl and dl.get('alerts')} found_run={dl and dl.get('found_run')}"
                       if dl is not None else proc.tail(20))

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
