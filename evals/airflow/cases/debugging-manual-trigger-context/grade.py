"""Grader for debugging-manual-trigger-context.

The fixture DAG breaks on Airflow 3.3 in three runtime-only ways: a removed
context key (`execution_date`), `context["logical_date"]` on manual runs that
have no logical date, and a `{{ ds_nodash }}` template that is undefined on
those runs. The grader executes the DAG twice in separate metadata DBs:

- a dated run (`airflow dags test partner_feed 2026-03-02`), which must produce
  the 2026-03-02 feed;
- a manual run with no logical date (`dag.test(logical_date=None,
  run_after=2026-03-03T00:30Z)`), which must produce the feed for the day it
  was triggered for (2026-03-03, UTC) and nothing else. The run is executed as
  if it had been cleared and re-run the next day (its DagRun ``start_date`` is
  2026-03-04), so the wall clock and ``start_date`` cannot stand in for the
  trigger day.

Both runs use a US local timezone (``TZ``), so a day taken in local time
instead of UTC lands on the wrong date.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

DAG_ID = "partner_feed"
DATED_DAY = "2026-03-02"
MANUAL_RUN_AFTER = "2026-03-03T00:30:00+00:00"
# Start of the "cleared and re-run tomorrow" execution of the manual run.
RERUN_START = "2026-03-04T09:00:00+00:00"
# Worker local time; 00:30 UTC on 03-03 is still 03-02 here.
LOCAL_TZ = {"TZ": "America/Los_Angeles"}
MANUAL_DAY = "2026-03-03"
CHAIN = ["extract_orders", "write_manifest", "deliver"]
FEED_COLUMNS = ["order_id", "sku", "qty", "amount"]


def expected_rows(day: str) -> list[dict]:
    with (CASE_DIR / "fixture" / "data" / "partner_orders.csv").open(newline="") as fh:
        return [{c: r[c] for c in FEED_COLUMNS} for r in csv.DictReader(fh)
                if r["order_date"] == day and r["partner"] == "acme"]


def read_csv(path: Path):
    if not path.is_file():
        return f"missing {path.name}"
    with path.open(newline="") as fh:
        return [{c: (r.get(c) or "").strip() for c in FEED_COLUMNS} for r in csv.DictReader(fh)]


def read_manifest(path: Path):
    if not path.is_file():
        return f"missing {path.name}"
    try:
        data = json.loads(path.read_text())
    except ValueError as exc:
        return f"invalid json: {exc}"
    return {"partition": data.get("partition"), "row_count": data.get("row_count")}


def check_outputs(ws: Path, day: str) -> tuple[bool, str]:
    """Feed, manifest and outbox copies for ``day`` are correct and no other day was produced."""
    rows = expected_rows(day)
    want_manifest = {"partition": day, "row_count": len(rows)}
    stamp = day.replace("-", "")
    feed_dir = ws / "output" / "partner_feed"
    outbox = ws / "outbox" / "acme"
    got = {
        "feed": read_csv(feed_dir / day / "orders.csv"),
        "manifest": read_manifest(feed_dir / day / "manifest.json"),
        "outbox_feed": read_csv(outbox / f"acme_orders_{stamp}.csv"),
        "outbox_manifest": read_manifest(outbox / f"acme_orders_{stamp}.manifest.json"),
    }
    problems = [k for k, want in (("feed", rows), ("manifest", want_manifest),
                                  ("outbox_feed", rows), ("outbox_manifest", want_manifest))
                if got[k] != want]
    other_days = sorted(p.name for p in feed_dir.iterdir() if p.name != day) if feed_dir.is_dir() else []
    other_files = sorted(p.name for p in outbox.iterdir() if stamp not in p.name) if outbox.is_dir() else []
    if other_days or other_files:
        problems.append(f"outputs for other days: {other_days + other_files}")
    detail = "ok" if not problems else (
        f"problems={problems}; expected {len(rows)} rows + manifest {want_manifest}; "
        f"got {json.dumps(got)[:1500]}")
    return not problems, detail


def clean_outputs(ws: Path) -> None:
    for sub in ("output", "outbox"):
        shutil.rmtree(ws / sub, ignore_errors=True)


def reachable(dag: dict, src: str, dst: str) -> bool:
    details, seen, stack = dag["task_details"], set(), [src]
    while stack:
        for nxt in details.get(stack.pop(), {}).get("downstream", []):
            if nxt == dst:
                return True
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


MANUAL_PROBE = """
import pendulum
from unittest import mock
import airflow.models.dagrun as dagrun_mod
dag = get_dag({dag_id!r})
_create = dagrun_mod.get_or_create_dagrun
def _rerun_next_day(**kw):
    # dag.test() starts the run at run_after; a run cleared and re-run the next
    # day starts later, so its start_date no longer matches the trigger time.
    kw["start_date"] = pendulum.parse({rerun_start!r})
    return _create(**kw)
with mock.patch.object(dagrun_mod, "get_or_create_dagrun", _rerun_next_day):
    dr = dag.test(logical_date=None, run_after=pendulum.parse({run_after!r}))
RESULT = {{"state": str(getattr(dr.state, "value", dr.state)),
          "logical_date": None if dr.logical_date is None else dr.logical_date.isoformat(),
          "run_after": dr.run_after.isoformat()}}
"""


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    imp = g.import_dags(py, ws)
    grader.primary("DAGs import cleanly", imp["ok"] and not imp["import_errors"],
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items()))
    dag = imp["dags"].get(DAG_ID)
    grader.primary(f"DAG {DAG_ID} is present", dag is not None, f"found: {sorted(imp['dags'])}")
    if dag is not None:
        missing = [t for t in CHAIN if t not in dag["tasks"]]
        broken = [f"{a}->{b}" for a, b in zip(CHAIN, CHAIN[1:])
                  if a in dag["tasks"] and b in dag["tasks"] and not reachable(dag, a, b)]
        grader.primary("task graph preserved (extract -> manifest -> deliver)", not missing and not broken,
                       f"missing={missing} broken={broken} deps={dag['deps']}")

        # Dated run: the logical date decides the day, not the wall clock.
        clean_outputs(ws)
        dated = g.run_dags_test(py, ws, DAG_ID, DATED_DAY, env=g.airflow_env(ws, extra=LOCAL_TZ))
        grader.primary(f"dags test with logical date {DATED_DAY} succeeds", dated.ok,
                       "" if dated.ok else f"failed tasks={dated.failed_tasks()}\n{dated.log[-3000:]}")
        ok, detail = check_outputs(ws, DATED_DAY)
        grader.primary(f"dated run delivers the {DATED_DAY} feed", ok, detail)

        # Manual run with no logical date, as the UI/API trigger creates in Airflow 3.
        clean_outputs(ws)
        env = g.airflow_env(ws, extra=LOCAL_TZ)
        db = g.ensure_db(py, env)
        res, proc = (None, db) if not db.ok else g.probe_json(
            py, MANUAL_PROBE.format(dag_id=DAG_ID, run_after=MANUAL_RUN_AFTER, rerun_start=RERUN_START), ws, env=env)
        runs = g.dag_runs(py, ws, DAG_ID, env) if db.ok else []
        failed = [t for r in runs for t, s in r.get("tasks", {}).items() if s != "success"]
        manual_ok = (res is not None and res.get("state") == "success" and res.get("logical_date") is None
                     and not failed)
        grader.primary("manual run without a logical date succeeds", manual_ok,
                       f"result={res} non-success tasks={failed}" + ("" if manual_ok else "\n" + proc.tail(40)))
        ok, detail = check_outputs(ws, MANUAL_DAY)
        grader.primary(f"manual run delivers the feed for its trigger day ({MANUAL_DAY})", ok, detail)

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
