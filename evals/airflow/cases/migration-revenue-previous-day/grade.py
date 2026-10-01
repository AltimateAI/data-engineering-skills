"""Grader for migration-revenue-previous-day.

The fixture is an Airflow 2.11 project; the agent migrates it to 3.3. Behaviour
is compared against the ORIGINAL project executed in the 2.11 env:

- the scheduled runs that fire at 04:15 UTC on 2026-03-05 and 2026-03-06 are
  replayed in both envs (``migsim``) and must write the same files with the same
  revenue figures (same business day: the day BEFORE the fire time);
- the DAGs import in 3.3, ``airflow dags test`` succeeds, the task graph is
  preserved and the project's own pytest suite passes on 3.3;
- the migrated suite is still a real CI gate: with a planted DAG file that does
  not import, it must fail (a skipped or gutted suite passes vacuously).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR))
import migsim  # noqa: E402

g = migsim.g
DAG_ID = "daily_revenue"
RUN_AFTERS = ["2026-03-05T04:15:00+00:00", "2026-03-06T04:15:00+00:00"]
EXPECTED_DEPS = [["load_daily_revenue", "publish_manifest"]]
PLANTED_NAME = "zz_planted_broken.py"
PLANTED_DAG = '''"""Planted by the grader: a DAG file whose import fails."""
import pendulum
from airflow.sdk import DAG
import finance_helpers_that_do_not_exist  # noqa: F401

with DAG(dag_id="planted_broken", schedule=None, start_date=pendulum.datetime(2026, 1, 1, tz="UTC")):
    pass
'''


def normalise(snap: dict[str, str]) -> dict[str, str]:
    """Manifests: only ``business_date`` is contractual (the timestamp format may change)."""
    out = {}
    for path, text in snap.items():
        if path.startswith("manifests/"):
            try:
                text = json.dumps({"business_date": json.loads(text).get("business_date")})
            except ValueError:
                text = f"<invalid json> {text[:200]}"
        out[path] = text
    return out


def migrated_env(py: str, ws: Path) -> dict:
    """Fresh AIRFLOW_HOME with a migrated metadata DB, as the team's CI has.

    The original suite already needs it on 2.11 (``DagBag.get_dag`` queries the
    ``dag`` table), so a migrated suite that keeps ``get_dag`` must not fail here
    just because the grader skipped ``airflow db migrate``.
    """
    env = g.airflow_env(ws, env_py=py)
    db = g.ensure_db(py, env)
    if not db.ok:
        raise SystemExit(f"grader: airflow db migrate failed: {db.tail(20)}")
    return env


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    # Ground truth: the untouched Airflow 2 project, run by the 2.11 scheduler logic.
    orig_ws, orig, orig_log = migsim.run_original(CASE_DIR, DAG_ID, RUN_AFTERS)
    if not migsim.runs_ok(orig):
        raise SystemExit(f"case bug: original project failed in 2.11: {migsim.describe(orig)}\n{orig_log}")
    expected = normalise(migsim.snapshot(orig_ws))

    imp = g.import_dags(py, ws)
    dag = imp["dags"].get(DAG_ID)
    grader.primary("DAGs import cleanly on Airflow 3.3",
                   imp["ok"] and not imp["import_errors"]
                   and {DAG_ID, "region_reference"} <= set(imp["dags"]),
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items())
                   or f"dags: {sorted(imp['dags'])}")
    grader.primary("daily_revenue keeps its tasks and dependency",
                   dag is not None and dag["deps"] == EXPECTED_DEPS
                   and set(dag["tasks"]) == {"load_daily_revenue", "publish_manifest"},
                   f"tasks={dag and dag['tasks']} deps={dag and dag['deps']}")

    shutil.rmtree(ws / "output", ignore_errors=True)
    if dag is not None:
        # `airflow dags test <dag> <date>` semantics (manual run), retries forced to 0.
        cli, cli_log = migsim.simulate(py, ws, DAG_ID, [migsim.manual("2026-03-05")])
        ref, ref_log = migsim.simulate(py, ws, "region_reference", [migsim.manual("2026-03-05")])
        ok = migsim.runs_ok(cli) and migsim.runs_ok(ref)
        grader.primary("dags test succeeds (daily_revenue, region_reference)", ok,
                       "" if ok else f"daily_revenue: {migsim.describe(cli)}\nregion_reference: "
                       f"{migsim.describe(ref)}\n{(cli_log if not migsim.runs_ok(cli) else ref_log)[-2500:]}")

        shutil.rmtree(ws / "output", ignore_errors=True)
        sim, sim_log = migsim.simulate(py, ws, DAG_ID, RUN_AFTERS, block_orm=True)
        grader.primary("scheduled 04:15 runs succeed on 3.3", migsim.runs_ok(sim),
                       migsim.describe(sim) + ("" if migsim.runs_ok(sim) else "\n" + sim_log[-2500:]))
        got = normalise(migsim.snapshot(ws))
        grader.primary("scheduled runs process the same business day and write the same output as 2.11",
                       got == expected, f"expected {expected}\n got {got}")
    else:
        grader.primary("dags test succeeds (daily_revenue, region_reference)", False, "DAG missing")

    tests = g.run_pytest(py, ws, ["tests"], env=migrated_env(py, ws))
    grader.primary("project test suite passes on 3.3", tests.status == "passed", tests.summary()
                   + ("" if tests.status == "passed" else "\n" + tests.output_tail[-1500:]))
    # The suite is the team's CI gate: a migrated suite that is skipped, gutted or
    # no longer parses the DAG folder passes vacuously. Plant a DAG file that cannot
    # be imported and require the suite to fail.
    planted_ws = Path(tempfile.mkdtemp(prefix="eval-planted-")) / "ws"
    shutil.copytree(ws, planted_ws, ignore=shutil.ignore_patterns("output", ".git", "__pycache__", "*.pyc"))
    (planted_ws / "dags" / PLANTED_NAME).write_text(PLANTED_DAG)
    planted = g.run_pytest(py, planted_ws, ["tests"], env=migrated_env(py, planted_ws))
    caught = tests.status == "passed" and planted.status in ("failed", "collection_error")
    grader.primary("project test suite still fails on a DAG file that does not import", caught,
                   f"clean: {tests.status}; with planted dags/{PLANTED_NAME}: {planted.summary()}")

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
