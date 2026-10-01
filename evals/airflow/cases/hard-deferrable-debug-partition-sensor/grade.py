"""Grader for hard-deferrable-debug-partition-sensor (Airflow 3.3).

The agent fixes the root causes behind seven production incidents in a deferrable sensor.
Grading drives the agent's PartitionPublishedSensor through hidden scenarios with grader-only
DAGs (grader_data/eval_dags/) against a grader-owned catalog API (grader_data/lake_api.py,
every request takes 0.5 s), using `airflow dags test` wrapped by grader_data/defer_runner.py
(deferral timeouts enforced with a 4 s grace, triggerer restart mid-wait, event-loop stall
measurement; see that file).

Scenarios (each with its own API server and metadata DB, run in parallel):
  wait       partition published 4 s after start; sensor must defer, return its files, never stall the loop
  timeout    never published, sensor timeout=10 s, retries=2, triggerer restarted 8 s into the wait
  softfail   never published, timeout=6 s, soft_fail=True
  outage     every request answers 503
  two_days   sensors for D and D-1 of the same table in one run
  budget     6 s upstream task, timeout=16 s, retries=4, 503s 3-8 s after the first request
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CASE_DIR = Path(os.path.abspath(__file__)).parent  # no resolve(): a symlinked case dir stays as given
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

GD = CASE_DIR / "grader_data"
TOKEN = "eval-lake-token"
LATENCY_S = 0.5
STALL_FAIL_S = 0.35
DAY, PREV = "2026-09-29", "2026-09-28"
TIMEOUT_S = 10.0
FAIL_WINDOW = (TIMEOUT_S - 1.5, TIMEOUT_S + 7.0)  # trigger deadline, or defer timeout + 4 s grace
RUN_TIMEOUT_S = 400
BUDGET_S = 16.0  # budget scenario: 6 s upstream task, sensor timeout=16 s, retries=4, 503s 3-8 s in

SCENARIOS = {
    "wait": dict(server=["--publish", f"orders/{DAY}=4"], dag="eval_lake_wait"),
    "timeout": dict(server=[], dag="eval_lake_timeout", env={"EVAL_RESTART_AFTER_S": "8"}),
    "softfail": dict(server=[], dag="eval_lake_softfail"),
    "outage": dict(server=["--down"], dag="eval_lake_outage"),
    "budget": dict(server=["--outage", "3", "8"], dag="eval_lake_budget"),
    "two_days": dict(server=["--publish", f"orders/{DAY}=0", "--publish", f"orders/{PREV}=0"],
                     dag="eval_lake_two_days"),
}

TI_PROBE = r'''
import sqlite3, os
db = os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"].split("sqlite:///", 1)[1]
con = sqlite3.connect(db)
rows = con.execute("SELECT dag_id, task_id, map_index, state, try_number FROM task_instance").fetchall()
RESULT = [dict(zip(["dag_id", "task_id", "map_index", "state", "try_number"], r)) for r in rows]
'''


def files_for(table: str, partition: str) -> list[str]:
    return [f"s3://lake/{table}/{partition}/part-{i}.parquet" for i in range(2)]


def read_jsonl(path: Path) -> list[dict]:
    out = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def run_scenario(py: str, ws: Path, name: str, spec: dict) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix=f"eval-lake-{name}-"))
    port_file, api_log, defer_log, out_dir = tmp / "port", tmp / "api.jsonl", tmp / "defer.jsonl", tmp / "out"
    out_dir.mkdir()
    server = subprocess.Popen(
        [py, str(GD / "lake_api.py"), "--port-file", str(port_file), "--log", str(api_log),
         "--latency", str(LATENCY_S), *spec["server"]],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        for _ in range(100):
            if port_file.exists() and port_file.read_text().strip():
                break
            time.sleep(0.1)
        port = int(port_file.read_text().strip())
        env = g.airflow_env(ws, env_py=py, extra={
            "AIRFLOW_CONN_LAKE_DEFAULT": json.dumps(
                {"conn_type": "http", "host": "127.0.0.1", "port": port, "password": TOKEN}),
            "EVAL_OUT_DIR": str(out_dir),
            "EVAL_DEFER_LOG": str(defer_log),
            **spec.get("env", {}),
        })
        db = g.ensure_db(py, env)
        if not db.ok:
            return {"name": name, "error": "db migrate failed: " + db.tail(20)}
        res = g.run_cmd([py, str(GD / "defer_runner.py"), "dags", "test", spec["dag"], DAY],
                        env=env, cwd=ws, timeout=RUN_TIMEOUT_S)
        tis, _ = g.probe_json(py, TI_PROBE, ws, env=env)
        outputs = {p.stem: json.loads(p.read_text()) for p in out_dir.glob("*.json")}
        return {"name": name, "api": read_jsonl(api_log), "defer": read_jsonl(defer_log), "tis": tis or [],
                "outputs": outputs, "log": res.output[-8000:] + ("\n[timed out]" if res.timed_out else "")}
    finally:
        server.kill()
        server.wait()


def ti(r: dict, task_id: str) -> dict:
    return next((t for t in r.get("tis", []) if t["task_id"] == task_id), {})


def brief(r: dict) -> str:
    trig = [{k: v for k, v in e.items() if k in ("kind", "task_id", "try_number", "waited_s", "payload", "timeout_s",
                                                  "state", "stalls")}
            for e in r.get("defer", [])]
    return json.dumps({"tis": [(t["task_id"], t["state"], t["try_number"]) for t in r.get("tis", [])],
                       "outputs": r.get("outputs"), "events": trig[:14]}, default=str)[:2500]


def log_tail(r: dict, n: int = 2000) -> str:
    keep = [ln for ln in r.get("log", "").splitlines()
            if any(k in ln for k in ("Error", "Exception", "Traceback", "raise ", "File \"", "timed out"))]
    return "\n".join(keep)[-n:]


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)

    penv = g.airflow_env(ws, env_py=py)
    penv["PYTHONPATH"] = os.pathsep.join((str(ws / "dags"), penv["PYTHONPATH"]))
    imp = g.import_dags(py, ws, env=penv)
    errs = "; ".join(f"{k}: {v.strip().splitlines()[-1]}" for k, v in imp["import_errors"].items())
    grader.primary("DAGs import cleanly", imp["ok"] and not imp["import_errors"]
                   and {"lake_ingest", "orders_diff"} <= set(imp["dags"]),
                   imp["probe_error"] or errs or f"dags: {sorted(imp['dags'])}")

    run_ws = g.copy_workspace(ws)
    shutil.copy2(GD / "eval_dags" / "_eval_lake_scenarios.py", run_ws / "dags" / "_eval_lake_scenarios.py")
    with cf.ThreadPoolExecutor(max_workers=len(SCENARIOS)) as ex:
        futs = {n: ex.submit(run_scenario, py, run_ws, n, s) for n, s in SCENARIOS.items()}
        R = {n: f.result() for n, f in futs.items()}

    w = R["wait"]
    deferred = any(e["kind"] == "defer" for e in w.get("defer", []))
    ok = ti(w, "wait").get("state") == "success" and w["outputs"].get(f"wait_{DAY}") == files_for("orders", DAY)
    grader.primary("sensor still defers and returns the published files", ok and deferred,
                   f"deferred={deferred}\n" + brief(w) + ("" if ok else "\n" + log_tail(w)))

    stalls = sorted((s for r in R.values() for e in r.get("defer", []) if e["kind"].startswith("trigger_")
                     for s in e.get("stalls", [])), reverse=True)
    big = [s for s in stalls if s >= STALL_FAIL_S]
    ran = sum(1 for r in R.values() for e in r.get("defer", []) if e["kind"].startswith("trigger_"))
    grader.primary("trigger never blocks the event loop (catalog API answers in 0.5 s)", ran > 0 and len(big) < 2,
                   f"{ran} trigger runs; stalls >= {STALL_FAIL_S}s: {big[:10]}")

    t = R["timeout"]
    t_ti = ti(t, "wait")
    defers = [e for e in t.get("defer", []) if e["kind"] == "defer" and e["task_id"] == "wait"]
    ends = [e for e in t.get("defer", []) if e["kind"] == "task_end" and e["task_id"] == "wait"]
    restarted = any(e["kind"] == "restart" for e in t.get("defer", []))
    dt = round(ends[0]["t"] - defers[0]["t"], 2) if defers and ends else None
    ok = (t_ti.get("state") == "failed" and t_ti.get("try_number") == 1)
    grader.primary("a timed-out sensor fails for good (no retries)", ok,
                   brief(t) + ("" if ok else "\n" + log_tail(t)))
    in_window = dt is not None and FAIL_WINDOW[0] <= dt <= FAIL_WINDOW[1]
    grader.primary("triggerer restart does not extend the sensor timeout", restarted and in_window
                   and t_ti.get("state") == "failed",
                   f"restart happened={restarted}; first try ended {dt}s after deferring "
                   f"(timeout={TIMEOUT_S}s, want {FAIL_WINDOW[0]}-{FAIL_WINDOW[1]}s)\n" + brief(t))

    s = R["softfail"]
    ok = ti(s, "wait").get("state") == "skipped"
    grader.primary("soft_fail sensor is skipped when it times out", ok, brief(s) + ("" if ok else "\n" + log_tail(s)))

    o = R["outage"]
    ok = ti(o, "wait").get("state") == "failed" and ti(o, "collect").get("state") != "success" \
        and not o["outputs"]
    grader.primary("API errors fail the sensor instead of letting the load run", ok,
                   brief(o) + ("" if ok else "\n" + log_tail(o)))

    bu = R["budget"]
    starts = [e for e in bu.get("defer", []) if e["kind"] == "worker_run" and e["task_id"] == "wait"]
    ends = [e for e in bu.get("defer", []) if e["kind"] == "task_end" and e["task_id"] == "wait"]
    span = round(ends[-1]["t"] - starts[0]["t"], 2) if starts and ends else None
    tries = ti(bu, "wait").get("try_number", 0)
    lo, hi = BUDGET_S - 1.5, BUDGET_S + 5.5
    ok = ti(bu, "wait").get("state") == "failed" and tries >= 2 and span is not None and lo <= span <= hi
    grader.primary("timeout is one budget per DAG run: a retry after an outage does not restart it", ok,
                   f"sensor ran from first try start to final failure in {span}s over {tries} tries "
                   f"(timeout={BUDGET_S}s, want {lo}-{hi}s)\n" + brief(bu) + ("" if ok else "\n" + log_tail(bu)))

    d = R["two_days"]
    want = {f"today_{DAY}": files_for("orders", DAY), f"yesterday_{DAY}": files_for("orders", PREV)}
    ok = all(d["outputs"].get(k) == v for k, v in want.items())
    grader.primary("sensors for two partitions of one table each get their own files", ok,
                   f"want={want}\n" + brief(d) + ("" if ok else "\n" + log_tail(d)))

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
