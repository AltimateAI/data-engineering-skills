"""Grader for migration-inventory-context.

The fixture is an Airflow 2.11 project using removed context keys in ways ruff
does not see (callable kwargs ``execution_date``/``prev_ds``,
``get_current_context()["execution_date"]``, ``xcom_pull`` without
``task_ids``). Behaviour is compared with the ORIGINAL project replayed in the
2.11 env: the scheduled runs that fire at 2026-03-05 00:00 and 2026-03-06 00:00
UTC run back to back against one DB (the second snapshot's ``change`` column
depends on the first) and must write the same snapshot CSVs and audit records.
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
DAG_ID = "inventory_snapshot"
RUN_AFTERS = ["2026-03-05T00:00:00+00:00", "2026-03-06T00:00:00+00:00"]
EXPECTED_TASKS = {"build_snapshot", "audit_snapshot"}
EXPECTED_DEPS = [["build_snapshot", "audit_snapshot"]]


def normalise(snap: dict[str, str]) -> dict[str, str]:
    out = {}
    for path, text in snap.items():
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

    orig_ws, orig, orig_log = migsim.run_original(CASE_DIR, DAG_ID, RUN_AFTERS)
    if not migsim.runs_ok(orig):
        raise SystemExit(f"case bug: original project failed in 2.11: {migsim.describe(orig)}\n{orig_log}")
    expected = normalise(migsim.snapshot(orig_ws))
    if not any(p.startswith("audit/") for p in expected):
        raise SystemExit(f"case bug: original wrote no audit records: {expected}")

    imp = g.import_dags(py, ws)
    dag = imp["dags"].get(DAG_ID)
    grader.primary("DAGs import cleanly on Airflow 3.3", imp["ok"] and not imp["import_errors"] and dag is not None,
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items())
                   or f"dags: {sorted(imp['dags'])}")
    grader.primary("inventory_snapshot keeps its tasks and dependency",
                   dag is not None and set(dag["tasks"]) == EXPECTED_TASKS and dag["deps"] == EXPECTED_DEPS,
                   f"tasks={dag and dag['tasks']} deps={dag and dag['deps']}")

    if dag is None:
        grader.primary("dags test succeeds", False, "DAG missing")
    else:
        shutil.rmtree(ws / "output", ignore_errors=True)
        cli, cli_log = migsim.simulate(py, ws, DAG_ID, [migsim.manual("2026-03-05")])
        grader.primary("dags test succeeds", migsim.runs_ok(cli),
                       migsim.describe(cli) + ("" if migsim.runs_ok(cli) else "\n" + cli_log[-2500:]))

        shutil.rmtree(ws / "output", ignore_errors=True)
        sim, sim_log = migsim.simulate(py, ws, DAG_ID, RUN_AFTERS, block_orm=True)
        grader.primary("consecutive scheduled daily runs succeed on 3.3", migsim.runs_ok(sim),
                       migsim.describe(sim) + ("" if migsim.runs_ok(sim) else "\n" + sim_log[-2500:]))
        got = normalise(migsim.snapshot(ws))
        grader.primary("snapshots and audit records match the Airflow 2 output", got == expected,
                       f"expected {expected}\n got {got}")

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
