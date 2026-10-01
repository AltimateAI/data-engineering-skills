"""Grader for migration-shipments-assets.

The fixture is an Airflow 2.11 logistics project: an hourly incremental load
(``ingest_shipments``) that publishes a Dataset, and a Dataset-scheduled
consumer (``carrier_scorecard``). Airflow 3 breaks it in ways ruff only partly
sees: ``airflow.datasets`` is gone (ruff reports it, but only as a
"suggested update"), the loader reads its high-water mark with a metadata-DB
session (blocked for task code in Airflow 3; the natural XCom replacement with
``include_prior_dates=True`` returns a LIST once several runs exist), and the
consumer's Jinja ``ti.xcom_pull(key=...)`` without ``task_ids`` renders
``None`` on 3.x.

Behaviour is compared with the ORIGINAL project replayed in the 2.11 env: three
consecutive hourly runs of the loader against one metadata DB, then a run of
the scorecard. Task code runs with the Airflow 3 worker's metadata-DB block
emulated (``migsim``).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR))
import migsim  # noqa: E402

g = migsim.g
PRODUCER = "ingest_shipments"
CONSUMER = "carrier_scorecard"
RUN_AFTERS = ["2026-03-05T01:00:00+00:00", "2026-03-05T02:00:00+00:00", "2026-03-05T03:00:00+00:00"]
CONSUMER_RUN = migsim.manual("2026-03-05T03:30:00+00:00")
EXPECTED_TASKS = {PRODUCER: ({"load_batch"}, []),
                  CONSUMER: ({"build_scorecard", "mark_ready"}, [["build_scorecard", "mark_ready"]])}

WIRING_PROBE = f"""
def keys(obj):
    # Asset -> uri/name keys; conditions (AssetAll/AssetAny) -> their members; refs -> name/uri.
    if hasattr(obj, "objects"):
        out = set()
        for o in obj.objects:
            out |= keys(o)
        return out
    out = set()
    if getattr(obj, "uri", None):
        out.add("uri:" + obj.uri)
    if getattr(obj, "name", None):
        out.add("name:" + obj.name)
    return out or {{"repr:" + repr(obj)}}

prod = get_dag({PRODUCER!r})
cons = get_dag({CONSUMER!r})
outlets = set()
for t in prod.tasks:
    for a in (t.outlets or []):
        outlets |= keys(a)
tt = cons.timetable
cond = getattr(tt, "asset_condition", None)
scheduled = keys(cond) if cond is not None else set()
RESULT = {{"outlets": sorted(outlets), "schedule_assets": sorted(scheduled), "timetable": type(tt).__name__}}
"""


def run_flow(py: str, ws: Path, block_orm: bool) -> tuple[dict, dict, str]:
    """Three hourly loads, then the scorecard, against one metadata DB."""
    env = g.airflow_env(ws, env_py=py)
    prod, prod_log = migsim.simulate(py, ws, PRODUCER, RUN_AFTERS, env=env, block_orm=block_orm)
    cons, cons_log = migsim.simulate(py, ws, CONSUMER, [CONSUMER_RUN], env=env, block_orm=block_orm)
    return prod, cons, (prod_log if not migsim.runs_ok(prod) else cons_log)


def split(snap: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    batches = {k: v for k, v in snap.items() if k.startswith("warehouse/")}
    reports = {k: v for k, v in snap.items() if k.startswith("scorecard/")}
    return batches, reports


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    orig_ws = migsim.original_workspace(CASE_DIR)
    prod, cons, log = run_flow(g.env_python("2.11"), orig_ws, block_orm=False)
    if not (migsim.runs_ok(prod) and migsim.runs_ok(cons)):
        raise SystemExit(f"case bug: original failed in 2.11: {migsim.describe(prod)} | "
                         f"{migsim.describe(cons)}\n{log}")
    exp_batches, exp_reports = split(migsim.snapshot(orig_ws))
    if len(exp_batches) != len(RUN_AFTERS) or "scorecard/_READY" not in exp_reports:
        raise SystemExit(f"case bug: unexpected original output {sorted(exp_batches)} {sorted(exp_reports)}")

    imp = g.import_dags(py, ws)
    dags = imp["dags"]
    grader.primary("DAGs import cleanly on Airflow 3.3",
                   imp["ok"] and not imp["import_errors"] and {PRODUCER, CONSUMER} <= set(dags),
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items())
                   or f"dags: {sorted(dags)}")
    shape_ok = all(d in dags and set(dags[d]["tasks"]) == tasks and dags[d]["deps"] == deps
                   for d, (tasks, deps) in EXPECTED_TASKS.items())
    grader.primary("both DAGs keep their tasks and dependencies", shape_ok,
                   "; ".join(f"{d}: tasks={dags[d]['tasks']} deps={dags[d]['deps']}" if d in dags else f"{d}: missing"
                             for d in EXPECTED_TASKS))

    if not {PRODUCER, CONSUMER} <= set(dags):
        grader.primary("carrier_scorecard is still scheduled on the asset ingest_shipments updates", False,
                       "DAG missing")
        grader.primary("dags test succeeds (ingest_shipments, carrier_scorecard)", False, "DAG missing")
    else:
        wiring, proc = g.probe_json(py, WIRING_PROBE, ws, env=g.airflow_env(ws, env_py=py))
        wired = bool(wiring) and bool(set(wiring["outlets"]) & set(wiring["schedule_assets"]))
        grader.primary("carrier_scorecard is still scheduled on the asset ingest_shipments updates", wired,
                       str(wiring) if wiring is not None else proc.tail(20))

        shutil.rmtree(ws / "output", ignore_errors=True)
        p_cli, p_log = migsim.simulate(py, ws, PRODUCER, [migsim.manual("2026-03-05T01:00:00+00:00")],
                                       block_orm=True)
        c_cli, c_log = migsim.simulate(py, ws, CONSUMER, [migsim.manual("2026-03-05T01:30:00+00:00")],
                                       block_orm=True)
        ok = migsim.runs_ok(p_cli) and migsim.runs_ok(c_cli)
        grader.primary("dags test succeeds (ingest_shipments, carrier_scorecard)", ok,
                       "" if ok else f"{PRODUCER}: {migsim.describe(p_cli)}\n{CONSUMER}: {migsim.describe(c_cli)}\n"
                       f"{(p_log if not migsim.runs_ok(p_cli) else c_log)[-2500:]}")

        shutil.rmtree(ws / "output", ignore_errors=True)
        prod, cons, log = run_flow(py, ws, block_orm=True)
        runs_ok = migsim.runs_ok(prod) and migsim.runs_ok(cons)
        grader.primary("three hourly loads and the scorecard run succeed on 3.3", runs_ok,
                       f"{PRODUCER}: {migsim.describe(prod)}\n{CONSUMER}: {migsim.describe(cons)}"
                       + ("" if runs_ok else "\n" + log[-2500:]))
        got_batches, got_reports = split(migsim.snapshot(ws))
        grader.primary("every carrier event is loaded exactly once, in the same batches as 2.11",
                       got_batches == exp_batches,
                       f"expected batches {sorted(exp_batches)} "
                       f"(rows {[len(v.splitlines()) - 1 for v in exp_batches.values()]})\n"
                       f" got {sorted(got_batches)} (rows {[len(v.splitlines()) - 1 for v in got_batches.values()]})")
        grader.primary("scorecard and _READY marker match 2.11", got_reports == exp_reports,
                       f"expected {exp_reports}\n got {got_reports}")

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
