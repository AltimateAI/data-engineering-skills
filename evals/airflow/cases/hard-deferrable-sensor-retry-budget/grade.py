"""Grader for hard-deferrable-sensor-retry-budget (Airflow 3.3).

The agent makes PartnerManifestSensor deferrable while keeping `timeout` a per-DAG-run budget
counted from the first try. Grading drives the agent's sensor through hidden scenarios with
grader-only DAGs (grader_data/eval_dags/) against a grader-owned manifest API
(grader_data/manifest_api.py, 0.5 s per request), using `airflow dags test` wrapped by
grader_data/defer_runner.py (deferral timeouts enforced with a 4 s grace, triggerer restart
mid-wait, event-loop stalls measured; see that file).

Scenarios (each with its own API server and metadata DB, run in parallel):
  ok               manifest published 4 s after the first request
  budget           6 s upstream task, then the sensor (timeout=16 s, retries=4); every request
                   answers 503 from 3 s to 8 s after the first one; never published
  restart          timeout=12 s, retries=2, never published, triggerer restarted 8 s in
  softfail_outage  soft_fail=True, retries=3; 503 from 2 s to 6 s; published at 9 s
  softfail_timeout soft_fail=True, timeout=6 s, never published
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
TOKEN = "eval-manifest-token"
LATENCY_S = 0.5
STALL_FAIL_S = 0.35
DAY = "2026-09-29"
RUN_TIMEOUT_S = 400
BUDGET_S, RESTART_TIMEOUT_S = 16.0, 12.0
GRACE = (-1.5, 5.5)  # trigger-side deadline (poll granularity) .. defer timeout + 4 s grace

SCENARIOS = {
    "ok": dict(server=["--publish-after", "4"], dag="eval_manifest_ok"),
    "budget": dict(server=["--outage", "3", "8"], dag="eval_manifest_budget"),
    "restart": dict(server=[], dag="eval_manifest_restart", env={"EVAL_RESTART_AFTER_S": "8"}),
    "softfail_outage": dict(server=["--outage", "2", "6", "--publish-after", "9"], dag="eval_manifest_softfail_outage"),
    "softfail_timeout": dict(server=[], dag="eval_manifest_softfail_timeout"),
}

TI_PROBE = r'''
import sqlite3, os
db = os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"].split("sqlite:///", 1)[1]
con = sqlite3.connect(db)
rows = con.execute("SELECT dag_id, task_id, map_index, state, try_number FROM task_instance").fetchall()
RESULT = [dict(zip(["dag_id", "task_id", "map_index", "state", "try_number"], r)) for r in rows]
'''


def files_for(partner: str, ds: str) -> list[str]:
    return [f"s3://partners/{partner}/{ds}/batch-{i}.csv.gz" for i in range(3)]


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
    tmp = Path(tempfile.mkdtemp(prefix=f"eval-manifest-{name}-"))
    port_file, api_log, defer_log, out_dir = tmp / "port", tmp / "api.jsonl", tmp / "defer.jsonl", tmp / "out"
    out_dir.mkdir()
    server = subprocess.Popen(
        [py, str(GD / "manifest_api.py"), "--port-file", str(port_file), "--log", str(api_log),
         "--latency", str(LATENCY_S), *spec["server"]],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        for _ in range(100):
            if port_file.exists() and port_file.read_text().strip():
                break
            time.sleep(0.1)
        port = int(port_file.read_text().strip())
        env = g.airflow_env(ws, env_py=py, extra={
            "AIRFLOW_CONN_MANIFESTS_DEFAULT": json.dumps(
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


def ti(r: dict, task_id: str = "wait") -> dict:
    return next((t for t in r.get("tis", []) if t["task_id"] == task_id), {})


def recs(r: dict, kind: str, task_id: str = "wait") -> list[dict]:
    return [e for e in r.get("defer", []) if e["kind"] == kind and e.get("task_id") == task_id]


def wait_span(r: dict) -> float | None:
    """Seconds from the sensor's first worker start to its last task end."""
    starts, ends = recs(r, "worker_run"), recs(r, "task_end")
    return round(ends[-1]["t"] - starts[0]["t"], 2) if starts and ends else None


def brief(r: dict) -> str:
    ev = [{k: v for k, v in e.items() if k in ("kind", "task_id", "try_number", "waited_s", "payload", "timeout_s",
                                                "state", "via")}
          for e in r.get("defer", []) if e.get("task_id") == "wait"]
    n503 = sum(1 for e in r.get("api", []) if e.get("event") == "503")
    return json.dumps({"tis": [(t["task_id"], t["state"], t["try_number"]) for t in r.get("tis", [])],
                       "outputs": r.get("outputs"), "api_503s": n503, "events": ev[:16]}, default=str)[:2500]


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
    grader.primary("DAGs import cleanly", imp["ok"] and not imp["import_errors"] and "partner_ingest" in imp["dags"],
                   imp["probe_error"] or errs or f"dags: {sorted(imp['dags'])}")

    run_ws = g.copy_workspace(ws)
    shutil.copy2(GD / "eval_dags" / "_eval_manifest_scenarios.py", run_ws / "dags" / "_eval_manifest_scenarios.py")
    with cf.ThreadPoolExecutor(max_workers=len(SCENARIOS)) as ex:
        futs = {n: ex.submit(run_scenario, py, run_ws, n, s) for n, s in SCENARIOS.items()}
        R = {n: f.result() for n, f in futs.items()}

    o = R["ok"]
    deferred = bool(recs(o, "defer"))
    ok = ti(o).get("state") == "success" and o["outputs"].get("eval_manifest_ok") == files_for("acme", DAY)
    grader.primary("sensor defers and returns the manifest's file list", ok and deferred,
                   f"deferred={deferred}\n" + brief(o) + ("" if ok else "\n" + log_tail(o)))

    stalls = sorted((s for r in R.values() for e in r.get("defer", []) if e["kind"].startswith("trigger_")
                     for s in e.get("stalls", [])), reverse=True)
    big = [s for s in stalls if s >= STALL_FAIL_S]
    ran = sum(1 for r in R.values() for e in r.get("defer", []) if e["kind"].startswith("trigger_"))
    grader.primary("trigger never blocks the event loop (API answers in 0.5 s)", ran > 0 and len(big) < 2,
                   f"{ran} trigger runs; stalls >= {STALL_FAIL_S}s: {big[:10]}")

    b = R["budget"]
    span = wait_span(b)
    tries = ti(b).get("try_number", 0)
    lo, hi = BUDGET_S + GRACE[0], BUDGET_S + GRACE[1]
    ok = ti(b).get("state") == "failed" and tries >= 2 and span is not None and lo <= span <= hi
    grader.primary("timeout is one budget per DAG run: retries after an outage do not reset it", ok,
                   f"sensor ran from first try start to final failure in {span}s over {tries} tries "
                   f"(timeout={BUDGET_S}s, want {lo}-{hi}s)\n" + brief(b) + ("" if ok else "\n" + log_tail(b)))

    rs = R["restart"]
    span = wait_span(rs)
    lo, hi = RESTART_TIMEOUT_S + GRACE[0], RESTART_TIMEOUT_S + GRACE[1]
    restarted = bool(recs(rs, "restart"))
    ok_fail = ti(rs).get("state") == "failed" and ti(rs).get("try_number") == 1
    grader.primary("a timed-out sensor fails for good (no retries)", ok_fail, brief(rs) + ("" if ok_fail else "\n" + log_tail(rs)))
    grader.primary("triggerer restart does not extend the timeout", restarted and ok_fail and span is not None
                   and lo <= span <= hi,
                   f"restart happened={restarted}; ended {span}s after the sensor started (want {lo}-{hi}s)\n" + brief(rs))

    so = R["softfail_outage"]
    ok = ti(so).get("state") == "success" and so["outputs"].get("eval_manifest_softfail_outage") == files_for("acme", DAY)
    grader.primary("soft_fail sensor uses its retries for an API outage instead of skipping", ok,
                   brief(so) + ("" if ok else "\n" + log_tail(so)))

    st = R["softfail_timeout"]
    ok = ti(st).get("state") == "skipped"
    grader.primary("soft_fail sensor is skipped when its timeout runs out", ok, brief(st) + ("" if ok else "\n" + log_tail(st)))

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
