"""Grader for authoring-clickstream-claim-check (Airflow 3.3).

Primary checks: the DAG imports; extract -> transform -> load are separate
tasks in a chain; `airflow dags test` for two days writes correct page stats;
no XCom (or Variable) value written by the DAG exceeds MAX_XCOM_BYTES (the day's events
must travel by reference, e.g. a file path, not through XCom); a rerun
reproduces the output.
"""

from __future__ import annotations

import csv
import gzip
import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

DAG_ID = "clickstream_page_stats"
DAYS = ("2026-09-28", "2026-09-29")
FIXTURE_DATA = CASE_DIR / "fixture" / "data"
MAX_XCOM_BYTES = 48 * 1024  # the day's filtered events are ~1 MB as JSON; stats for 32 pages are ~2 KB
TOL = 0.051


def expected(day: str) -> dict[str, tuple[int, int, float]]:
    views: dict[str, int] = defaultdict(int)
    users: dict[str, set] = defaultdict(set)
    load: dict[str, int] = defaultdict(int)
    with gzip.open(FIXTURE_DATA / "clickstream" / f"{day}.csv.gz", "rt", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["is_bot"] == "1" or not r["user_id"]:
                continue
            views[r["page"]] += 1
            users[r["page"]].add(r["user_id"])
            load[r["page"]] += int(r["load_ms"])
    return {p: (views[p], len(users[p]), round(load[p] / views[p], 1)) for p in views}


def read_output(ws: Path, day: str) -> dict | str:
    path = ws / "output" / "page_stats" / f"{day}.csv"
    if not path.exists():
        return "missing"
    try:
        with path.open(newline="") as fh:
            return {r["page"]: (int(float(r["views"])), int(float(r["unique_users"])), float(r["avg_load_ms"]))
                    for r in csv.DictReader(fh)}
    except (KeyError, ValueError) as exc:
        return f"unreadable: {exc!r}"


def matches(got, want) -> bool:
    return isinstance(got, dict) and set(got) == set(want) and all(
        got[p][:2] == want[p][:2] and abs(got[p][2] - want[p][2]) <= TOL for p in want)


def xcom_sizes(env: dict) -> list[tuple[str, str, int]]:
    """(task_id, key, bytes) for every XCom row of the DAG, plus every Variable
    (task_id "<variable>"), in the grading metadata DB. Both live in the metadata DB,
    so stashing the events in a Variable is the same mistake as pushing them to XCom."""
    db = Path(env["AIRFLOW_HOME"]) / "airflow.db"
    with sqlite3.connect(db) as con:
        rows = con.execute(
            "SELECT task_id, key, length(CAST(value AS BLOB)) FROM xcom WHERE dag_id = ?", (DAG_ID,)
        ).fetchall()
        rows += con.execute("SELECT '<variable>', key, length(CAST(val AS BLOB)) FROM variable").fetchall()
    return [(t, k, n or 0) for t, k, n in rows]


def longest_chain(deps: list[list[str]], tasks: list[str]) -> int:
    down: dict[str, list[str]] = defaultdict(list)
    for u, d in deps:
        down[u].append(d)
    memo: dict[str, int] = {}

    def depth(t: str) -> int:
        if t not in memo:
            memo[t] = 1 + max((depth(d) for d in down[t]), default=0)
        return memo[t]

    return max((depth(t) for t in tasks), default=0)


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    for sub in ("output", "staging", "data"):
        shutil.rmtree(ws / sub, ignore_errors=True)
    shutil.copytree(FIXTURE_DATA, ws / "data")

    imp = g.import_dags(py, ws)
    dag = imp["dags"].get(DAG_ID)
    grader.primary("DAGs import cleanly", imp["ok"] and not imp["import_errors"],
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items()))
    grader.primary(f"DAG {DAG_ID} exists", dag is not None, f"found: {sorted(imp['dags'])}")
    if dag is None:
        g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
        grader.write(args.out)
        return

    chain = longest_chain(dag["deps"], dag["tasks"])
    grader.primary("extract, transform and load are separate chained tasks", chain >= 3,
                   f"longest dependency chain: {chain} tasks; deps={dag['deps']}")

    env = g.airflow_env(ws)
    runs = []
    for day in DAYS:
        runs.append(g.run_dags_test(py, ws, DAG_ID, day, env=env))
        if not runs[-1].ok:
            break
    all_ok = len(runs) == len(DAYS) and all(r.ok for r in runs)
    grader.primary("airflow dags test succeeds", all_ok,
                   "" if all_ok else f"failed tasks: {runs[-1].failed_tasks()}\n{runs[-1].log[-2500:]}")

    outputs = {d: read_output(ws, d) for d in DAYS}
    correct = all(matches(outputs[d], expected(d)) for d in DAYS)
    grader.primary("page stats are correct for each day", all_ok and correct,
                   "; ".join(f"{d}: expected {len(expected(d))} pages, got "
                             f"{outputs[d] if isinstance(outputs[d], str) else len(outputs[d])} "
                             f"(first mismatch: {_first_mismatch(outputs[d], expected(d))})" for d in DAYS))

    sizes = xcom_sizes(env) if runs else []
    biggest = max(sizes, key=lambda s: s[2], default=("-", "-", 0))
    grader.primary(f"no XCom/Variable value larger than {MAX_XCOM_BYTES // 1024} KB (data passed by reference)",
                   all_ok and biggest[2] <= MAX_XCOM_BYTES,
                   f"{len(sizes)} XCom/Variable rows; largest: task={biggest[0]} key={biggest[1]} bytes={biggest[2]}")

    again = g.run_dags_test(py, ws, DAG_ID, DAYS[0], env=env) if all_ok else None
    re_out = read_output(ws, DAYS[0])
    grader.primary("rerun reproduces the output", bool(again and again.ok) and matches(re_out, expected(DAYS[0])),
                   "skipped: first runs failed" if again is None else f"rerun ok={again.ok}")

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


def _first_mismatch(got, want) -> str:
    if not isinstance(got, dict):
        return str(got)
    for p in sorted(set(got) | set(want)):
        if p not in got or p not in want or not matches({p: got[p]}, {p: want[p]}):
            return f"{p}: expected {want.get(p)} got {got.get(p)}"
    return "none"


if __name__ == "__main__":
    main()
