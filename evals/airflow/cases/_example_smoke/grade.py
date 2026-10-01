"""Grader for _example_smoke (template for case authors).

Run: <airflow-3.3 python> grade.py --workspace DIR --events EVENTS.jsonl --out RESULT.json
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

DAG_ID = "event_counts"
DAY, NEIGHBOUR = "2026-03-01", "2026-03-02"


def expected_rows(day: str) -> list[list[str]]:
    """Ground truth from the pristine fixture data (never from the agent's workspace)."""
    counts: Counter[str] = Counter()
    with (CASE_DIR / "fixture" / "data" / "events.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["event_date"] == day:
                counts[row["event_type"]] += 1
    return [["event_type", "count"]] + [[k, str(counts[k])] for k in sorted(counts)]


def read_rows(path: Path) -> list[list[str]] | None:
    if not path.exists():
        return None
    with path.open(newline="") as fh:
        return [[c.strip() for c in r] for r in csv.reader(fh) if r]


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    imp = g.import_dags(py, ws)
    dag = imp["dags"].get(DAG_ID)
    grader.primary("DAGs import cleanly", imp["ok"] and not imp["import_errors"],
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items()))
    grader.primary(f"DAG {DAG_ID} exists", dag is not None, f"found: {sorted(imp['dags'])}")

    out_dir = ws / "output" / DAG_ID
    # Never grade files the agent produced by hand: only what the DAG writes counts.
    shutil.rmtree(ws / "output", ignore_errors=True)
    if dag is not None:
        env = g.airflow_env(ws)
        neighbour = g.run_dags_test(py, ws, DAG_ID, NEIGHBOUR, env=env)
        first = g.run_dags_test(py, ws, DAG_ID, DAY, env=env)
        grader.primary("airflow dags test succeeds", neighbour.ok and first.ok,
                       "" if first.ok and neighbour.ok else (first.log if not first.ok else neighbour.log)[-3000:])
        got = read_rows(out_dir / f"{DAY}.csv")
        grader.primary("output for the run date is correct", got == expected_rows(DAY),
                       f"expected {expected_rows(DAY)}, got {got}")
        second = g.run_dags_test(py, ws, DAG_ID, DAY, env=env)
        again = read_rows(out_dir / f"{DAY}.csv")
        grader.primary("re-run is idempotent and preserves other dates",
                       second.ok and again == expected_rows(DAY)
                       and read_rows(out_dir / f"{NEIGHBOUR}.csv") == expected_rows(NEIGHBOUR),
                       f"second run ok={second.ok}; after re-run {DAY}={again}; "
                       f"{NEIGHBOUR}={read_rows(out_dir / f'{NEIGHBOUR}.csv')}")

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
