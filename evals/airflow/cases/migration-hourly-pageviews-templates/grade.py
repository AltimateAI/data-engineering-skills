"""Grader for migration-hourly-pageviews-templates.

The fixture is an Airflow 2.11 hourly rollup whose templated fields use context
variables Airflow 3 removed: ``{{ execution_date }}``, ``{{ next_execution_date }}``,
``{{ prev_execution_date }}`` (PythonOperator ``op_kwargs``) and
``{{ yesterday_ds_nodash }}`` (BashOperator cleanup). Ruff's AIR rules do not
look inside Jinja strings. The bare cron "0 * * * *" also becomes
CronTriggerTimetable in Airflow 3, so the 10:00 run would no longer process
09:00-10:00.

Behaviour is compared with the ORIGINAL project replayed in the 2.11 env:
three scheduled runs (10:00 and 11:00 on 2026-03-05 and the midnight run on
2026-03-06) against one DB, starting from the same pre-seeded staging area.
The midnight run checks that the staging cleanup still targets the day before
the processed hour.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR))
import migsim  # noqa: E402

g = migsim.g
DAG_ID = "hourly_pageviews"
RUN_AFTERS = ["2026-03-05T10:00:00+00:00", "2026-03-05T11:00:00+00:00", "2026-03-06T00:00:00+00:00"]
EXPECTED_TASKS = {"extract_hour", "aggregate_hour", "publish_hour"}
EXPECTED_DEPS = [["aggregate_hour", "publish_hour"], ["extract_hour", "aggregate_hour"]]
SEED_STAGING = {
    "20260304T22.csv": "ts,session_id,page\n2026-03-04T22:15:00Z,s001,/\n",
    "20260304T23.csv": "ts,session_id,page\n2026-03-04T23:40:00Z,s002,/docs\n",
    "20260305T08.csv": "ts,session_id,page\n2026-03-05T08:05:00Z,s003,/pricing\n",
}


def seed(ws: Path) -> None:
    shutil.rmtree(ws / "output", ignore_errors=True)
    staging = ws / "output" / "staging"
    staging.mkdir(parents=True)
    for name, text in SEED_STAGING.items():
        (staging / name).write_text(text)


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    orig_ws, orig, orig_log = migsim.run_original(CASE_DIR, DAG_ID, RUN_AFTERS, prepare=seed)
    if not migsim.runs_ok(orig):
        raise SystemExit(f"case bug: original project failed in 2.11: {migsim.describe(orig)}\n{orig_log}")
    expected = migsim.snapshot(orig_ws)
    if "staging/20260304T22.csv" in expected or not any(p.startswith("markers/") for p in expected):
        raise SystemExit(f"case bug: unexpected original output {sorted(expected)}")

    imp = g.import_dags(py, ws)
    dag = imp["dags"].get(DAG_ID)
    grader.primary("DAG imports cleanly on Airflow 3.3", imp["ok"] and not imp["import_errors"] and dag is not None,
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items())
                   or f"dags: {sorted(imp['dags'])}")
    grader.primary("hourly_pageviews keeps its tasks and dependencies",
                   dag is not None and set(dag["tasks"]) == EXPECTED_TASKS
                   and {tuple(d) for d in EXPECTED_DEPS} <= {tuple(d) for d in dag["deps"]},
                   f"tasks={dag and dag['tasks']} deps={dag and dag['deps']}")

    if dag is None:
        grader.primary("dags test succeeds", False, "DAG missing")
    else:
        seed(ws)
        cli, cli_log = migsim.simulate(py, ws, DAG_ID, [migsim.manual("2026-03-05T10:00:00+00:00")], block_orm=True)
        grader.primary("dags test succeeds", migsim.runs_ok(cli),
                       migsim.describe(cli) + ("" if migsim.runs_ok(cli) else "\n" + cli_log[-2500:]))

        seed(ws)
        sim, sim_log = migsim.simulate(py, ws, DAG_ID, RUN_AFTERS, block_orm=True)
        grader.primary("scheduled hourly runs succeed on 3.3", migsim.runs_ok(sim),
                       migsim.describe(sim) + ("" if migsim.runs_ok(sim) else "\n" + sim_log[-2500:]))
        got = migsim.snapshot(ws)

        def part(snap: dict[str, str], prefix: str) -> dict[str, str]:
            return {k: v for k, v in snap.items() if k.startswith(prefix)}

        for prefix, label in (("hourly/", "hourly rollups (previous clock hour, change vs hour before) match 2.11"),
                              ("markers/", "completion markers match 2.11"),
                              ("staging/", "staging cleanup keeps and deletes the same files as 2.11")):
            exp_part, got_part = part(expected, prefix), part(got, prefix)
            if prefix == "staging/":
                detail = f"expected files {sorted(exp_part)}\n got {sorted(got_part)}"
            else:
                detail = f"expected {exp_part}\n got {got_part}"
            grader.primary(label, got_part == exp_part, detail)

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
