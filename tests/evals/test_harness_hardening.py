"""Harness hardening: signal isolation in the sandbox, broad-kill detection, runs killed
from outside (infra_error, retried), per-case timeout/turn limits and resume of killed runs."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import claude_code as cc
import grading as g
import isolation as iso
import pytest
import run_eval as r
from test_claude_code import AIRFLOW, FIXTURES, REPO, _Budget, _ctx, skill
from test_isolation import make_roots
from test_run_eval import STEP, classify, make_case

# --------------------------------------------------------------------------
# 1. Signal isolation (sandbox profile) and broad-kill detection
# --------------------------------------------------------------------------


def test_sandbox_profile_isolates_signals_by_default(tmp_path):
    prof = iso.sandbox_profile(write_allow=[tmp_path])
    assert prof.splitlines()[-2:] == ["(deny signal)", "(allow signal (target same-sandbox))"]
    assert "signal" not in iso.sandbox_profile(write_allow=[tmp_path], isolate_signals=False)
    for runner in ("altimate-code", "claude-code"):
        roots = make_roots(tmp_path)
        roots.runner = runner
        assert "(allow signal (target same-sandbox))" in roots.sandbox_profile()


@pytest.mark.skipif(not iso.sandbox_available(), reason="sandbox-exec not available")
@pytest.mark.parametrize("runner", ["altimate-code", "claude-code"])
def test_sandboxed_pkill_cannot_kill_outside_but_kills_own_children(tmp_path, runner):
    """Real sandbox-exec with the harness profile: ``pkill -f`` / ``kill`` of an outside process
    fails with EPERM, the agent's own children can still be signalled."""
    roots = make_roots(tmp_path)
    roots.runner = runner
    prof = tmp_path / "p.sb"
    prof.write_text(roots.sandbox_profile())
    tag = f"des-evals-sigprobe-{os.getpid()}-{runner}"
    outside = subprocess.Popen(["/bin/sh", "-c", f"exec -a {tag}-outside sleep 120"])
    try:
        time.sleep(0.3)
        script = (f"kill -TERM {outside.pid}; echo kill_rc=$?; "
                  f"pkill -f {tag}-outside; echo pkill_rc=$?; "
                  f"sleep 120 & c=$!; kill -TERM $c; wait $c; echo child_status=$?; "
                  f"(exec -a {tag}-child sleep 120) & c2=$!; sleep 0.3; pkill -f {tag}-child; echo pkill_child_rc=$?; "
                  f"wait $c2; echo child2_status=$?")
        res = subprocess.run(iso.sandbox_wrap(["/bin/bash", "-c", script], prof), capture_output=True, text=True,
                             timeout=60)
        out = res.stdout
        assert "kill_rc=1" in out and "pkill_rc=1" in out, out + res.stderr
        assert "Operation not permitted" in res.stderr
        assert "child_status=143" in out and "pkill_child_rc=0" in out and "child2_status=143" in out, out
        assert outside.poll() is None  # the outside process survived
    finally:
        outside.kill()
        outside.wait()


@pytest.mark.skipif(not iso.sandbox_available(), reason="sandbox-exec not available")
def test_sibling_sandbox_cannot_kill_another_sandboxed_run(tmp_path):
    """Two attempts under identical profiles are different sandbox instances."""
    prof = tmp_path / "p.sb"
    prof.write_text(make_roots(tmp_path).sandbox_profile())
    sibling = subprocess.Popen(iso.sandbox_wrap(["/bin/sleep", "120"], prof))
    try:
        time.sleep(0.3)
        res = subprocess.run(iso.sandbox_wrap(["/bin/sh", "-c", f"kill -TERM {sibling.pid}"], prof),
                             capture_output=True, text=True, timeout=30)
        assert res.returncode != 0 and "Operation not permitted" in res.stderr
        assert sibling.poll() is None
    finally:
        sibling.kill()
        sibling.wait()


@pytest.mark.parametrize("cmd,labels", [
    ("pkill -f airflow", ["pkill"]),
    ("pkill -9 -f agent-airflow || true", ["pkill"]),
    ("sleep 1; killall python3", ["killall"]),
    ("kill -9 $(pgrep -f 'airflow scheduler')", ["kill-substitution"]),
    ("kill `pgrep airflow`", ["kill-substitution"]),
    ("kill -9 $(lsof -ti:8080)", ["kill-substitution"]),
    ("ps aux | grep airflow | awk '{print $2}' | xargs kill -9", ["xargs-kill"]),
    ("pgrep -f triggerer | xargs -r kill", ["xargs-kill"]),
    ("kill -9 -1", ["kill-all-pids"]),
    ("kill -- -1; echo", ["kill-all-pids"]),
])
def test_kill_patterns_flag_broad_kills(cmd, labels):
    assert iso.kill_patterns(cmd) == labels


@pytest.mark.parametrize("cmd", [
    "kill $!", "kill -9 12345", "kill -TERM \"$PID\"", "airflow dags test x", "echo skill", "ps aux | grep airflow",
    "pgrep -f airflow", "python -c 'import os; os.kill(os.getpid(), 0)'", "cat backfill.log", "kill -1 4242",
    "pytest -k 'not kill'",
])
def test_kill_patterns_ignore_targeted_or_unrelated(cmd):
    assert iso.kill_patterns(cmd) == []


def test_scan_kill_commands_and_isolation_report(tmp_path):
    calls = [{"tool": "bash", "input": {"command": "pkill -f airflow"}, "output": "pkill: Operation not permitted"},
             {"tool": "bash", "input": {"command": "kill $!"}, "output": ""},
             {"tool": "read", "input": {"file_path": "/x/pkill.md"}, "output": ""}]
    hits = iso.scan_kill_commands(calls)
    assert [(h["call"], h["patterns"]) for h in hits] == [(0, ["pkill"])]
    assert "Operation not permitted" in hits[0]["output"]
    events = [{"type": "tool_use", "part": {"tool": "bash", "state": {"input": {"command": "killall airflow"},
                                                                     "output": "", "status": "completed"}}}]
    rep = r.isolation_report(events, make_roots(tmp_path))
    assert "kill_commands" in rep and "contamination_suspect" in rep


# --------------------------------------------------------------------------
# 2. Killed from outside -> infra_error (killed), retried at most twice
# --------------------------------------------------------------------------


def test_kill_signal_from_returncode():
    assert r.kill_signal(-15) == signal.SIGTERM and r.kill_signal(143) == signal.SIGTERM
    assert r.kill_signal(-9) == signal.SIGKILL and r.kill_signal(137) == signal.SIGKILL
    assert r.kill_signal(-2) == signal.SIGINT and r.kill_signal(129) == signal.SIGHUP
    for rc in (None, 0, 1, 2, 127, 128, -11, 139):
        assert r.kill_signal(rc) is None


def test_classify_killed_is_infra_error():
    fail = {"primary_pass": False, "checks": [{"name": "runs", "kind": "primary", "passed": False}]}
    for rc in (-15, -9, 143, 137):
        status, reason = r.classify_attempt(timed_out=False, cost_capped=False, returncode=rc, events=[STEP],
                                            stderr="", grade=fail, grader_failed=False)
        assert status == "infra_error" and reason.startswith("killed by signal"), (rc, reason)
        assert classify(returncode=rc, events=[]) == "infra_error"
    # the harness stopped it (timeout / cost cap): not "killed"
    assert classify(returncode=-15, timed_out=True, grade=fail) == "timeout"
    assert classify(returncode=-9, cost_capped=True, grade=fail) == "cost_limit"
    # the run finished (termination / result event) before the signal: graded normally
    term = {"type": "termination", "why_harness_stopped": "completed"}
    assert classify(returncode=143, events=[STEP, term], grade=fail) == "task_fail"
    assert classify(returncode=1, grade=fail) == "task_fail"


def test_classify_killed_claude_stream_without_result():
    events = [e for e in g.load_events(FIXTURES / "claude_stream_skill_run.jsonl") if e.get("type") != "result"]
    fail = {"primary_pass": False, "checks": [{"name": "runs", "kind": "primary", "passed": False}]}
    status, reason = r.classify_attempt(timed_out=False, cost_capped=False, returncode=143, events=events,
                                        stderr="", grade=fail, grader_failed=False)
    assert (status, reason.split(" (")[0]) == ("infra_error", "killed by signal 15")
    full = g.load_events(FIXTURES / "claude_stream_skill_run.jsonl")
    assert r.classify_attempt(timed_out=False, cost_capped=False, returncode=143, events=full, stderr="",
                              grade=fail, grader_failed=False)[0] == "task_fail"


KILLED = {"status": "infra_error", "reason": "killed by signal 15 (SIGTERM), rc=-15", "cost_usd": 0.3}


@pytest.mark.parametrize("runner", ["claude-code", "altimate-code"])
def test_attempt_loop_retries_killed_at_most_twice(runner):
    slept = []
    row = {"attempts": []}
    gate = cc.UsageLimitGate() if runner == "claude-code" else None
    r.attempt_loop(row, lambda k: dict(KILLED), _ctx(gate, runner=runner), _Budget(), "c m run-1",
                   sleep=slept.append)
    assert [a["status"] for a in row["attempts"]] == ["infra_error"] * 3
    assert all(a["killed"] for a in row["attempts"]) and len(slept) == 2
    fin = r.finalize_row({**row})
    assert fin["status"] == "infra_error" and fin["killed_attempts"] == 3 and fin["retries"] == 2
    assert fin["cost_usd"] == pytest.approx(0.9)


def test_attempt_loop_killed_then_ok():
    outcomes = iter([dict(KILLED), {"status": "ok", "reason": "primary checks passed", "cost_usd": 1.0}])
    row = {"attempts": []}
    r.attempt_loop(row, lambda k: next(outcomes), _ctx(cc.UsageLimitGate()), _Budget(), "c", sleep=lambda s: None)
    fin = r.finalize_row(row)
    assert [a["status"] for a in row["attempts"]] == ["infra_error", "ok"]
    assert fin["status"] == "ok" and fin["killed_attempts"] == 1


def _claude_args(tmp_path):
    flat = tmp_path / "flat"
    for n in REPO + AIRFLOW:
        skill(flat, n, n)
    args = r.argparse.Namespace(work_dir=tmp_path / "work", keep_workspaces=False, keep_traces=False,
                                max_run_cost_usd=None)
    args.work_dir.mkdir()
    args.ctx = r.AttemptContext(out_dir=None, work_dir=args.work_dir, staged_skills=tmp_path / "staged",
                                runner="claude-code", flat_skills=flat, arm="skill", airflow_names=AIRFLOW,
                                repo_names=REPO, usage_gate=cc.UsageLimitGate())
    return args


def test_run_attempt_killed_claude_run_is_not_graded(tmp_path, monkeypatch):
    case = r.load_case(make_case(tmp_path / "cases", "c1"))
    lines = (FIXTURES / "claude_stream_skill_run.jsonl").read_text().splitlines()
    partial = "\n".join(line for line in lines if '"type":"result"' not in line) + "\n"
    seen = {}

    def fake_process(cmd, cwd, env, events_path, stderr_path, timeout_s, cap, model, correct, spool_dir=None,
                     monitor_factory=None):
        seen["timeout_s"] = timeout_s
        events_path.write_text(partial + json.dumps({"type": "assistant", "message": {"id": "k", "content": [
            {"type": "tool_use", "id": "t9", "name": "Bash", "input": {"command": "pkill -f airflow"}}]}}) + "\n")
        stderr_path.write_text("")
        mon = monitor_factory(events_path)
        mon.poll()
        return {"returncode": -15, "timed_out": False, "cost_capped": False, "aborted": None, "wall_s": 3.0,
                "inventory": mon.inventory, "inventory_problems": mon.inventory_problems}

    monkeypatch.setattr(r, "run_agent_process", fake_process)
    monkeypatch.setattr(r.g, "agent_env_python", lambda v: str(tmp_path / "agent-env" / "bin" / "python"))
    monkeypatch.setattr(r, "run_grader", lambda *a, **k: pytest.fail("a killed run must not be graded"))
    args = _claude_args(tmp_path)
    rec = r.run_attempt(case, "claude-sonnet-5-5", "skill", tmp_path / "out" / "attempt-0", tmp_path / "staged",
                        set(AIRFLOW), args, _Budget())
    assert rec["status"] == "infra_error" and rec["reason"].startswith("killed by signal 15"), rec["reason"]
    assert rec["kill_command"] and rec["isolation"]["kill_commands"][0]["patterns"] == ["pkill"]
    assert rec["cost_usd"] > 0 and seen["timeout_s"] == case.timeout_s
    assert r.should_retry(rec) and args.ctx.abort_reason is None


def test_run_attempt_killed_altimate_run_is_not_graded(tmp_path, monkeypatch):
    case = r.load_case(make_case(tmp_path / "cases", "c1"))

    def fake_process(cmd, cwd, env, events_path, stderr_path, timeout_s, cap, model, correct, spool_dir=None):
        events_path.write_text(json.dumps(STEP) + "\n")
        stderr_path.write_text("")
        return {"returncode": 143, "timed_out": False, "cost_capped": False, "aborted": None, "wall_s": 2.0}

    monkeypatch.setattr(r, "run_agent_process", fake_process)
    monkeypatch.setattr(r.g, "agent_env_python", lambda v: str(tmp_path / "agent-env" / "bin" / "python"))
    monkeypatch.setattr(r, "run_grader", lambda *a, **k: pytest.fail("a killed run must not be graded"))
    args = r.argparse.Namespace(work_dir=tmp_path / "work", keep_workspaces=False, keep_traces=False,
                                max_run_cost_usd=None)
    args.work_dir.mkdir()
    rec = r.run_attempt(case, "google-vertex-anthropic/claude-haiku-4-5@20251001", "skill",
                        tmp_path / "out" / "attempt-0", tmp_path / "staged", set(), args, _Budget())
    assert rec["status"] == "infra_error" and rec["reason"].startswith("killed by signal 15")
    assert rec["kill_command"] is False


def test_run_agent_process_external_kill_reports_signal(tmp_path):
    """A real child killed by someone else: Popen reports ``-SIGTERM``; nothing marks it as
    a harness stop, so it classifies as killed."""
    proc_holder = {}

    def factory(path):
        class M:
            inventory = inventory_problems = abort_reason = None

            def poll(self):
                pid = proc_holder.get("pid")
                if pid is None:
                    out = subprocess.run(["pgrep", "-f", "des-evals-killprobe"], capture_output=True, text=True)
                    pids = [int(p) for p in out.stdout.split()]
                    if pids:
                        proc_holder["pid"] = pids[0]
                        os.kill(pids[0], signal.SIGTERM)
                return 0.0
        return M()

    script = "import sys,time\nsys.argv[0]='des-evals-killprobe'\ntime.sleep(60)\n"
    res = r.run_agent_process([sys.executable, "-c", script, "des-evals-killprobe"], tmp_path, dict(os.environ),
                              tmp_path / "e.jsonl", tmp_path / "s.log", 120, None, "m", False,
                              monitor_factory=factory)
    assert res["returncode"] == -signal.SIGTERM and not res["timed_out"] and not res["cost_capped"]
    assert r.classify_attempt(timed_out=False, cost_capped=False, returncode=res["returncode"], events=[],
                              stderr="", grade=None, grader_failed=False)[1].startswith("killed")


def test_killed_rows_are_rerun_on_resume(tmp_path):
    p = tmp_path / "runs.jsonl"
    rows = [{"case": "a", "model": "m", "run": 1, "status": "infra_error", "reason": KILLED["reason"],
             "attempts": [dict(KILLED)] * 3},
            {"case": "b", "model": "m", "run": 1, "status": "ok", "attempts": [{"status": "ok"}]}]
    p.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    done, redo = r.load_resume(p)
    assert set(redo) == {("a", "m", 1)} and set(done) == {("b", "m", 1)}


# --------------------------------------------------------------------------
# 3. Per-case timeout_s / max_turns up to 3600 s / 120 turns
# --------------------------------------------------------------------------


def _with_limits(tmp_path, **kw):
    d = make_case(tmp_path, "c1")
    text = (d / "case.yaml").read_text() + "".join(f"{k}: {v}\n" for k, v in kw.items())
    (d / "case.yaml").write_text(text)
    return d


def test_load_case_accepts_limits_up_to_max(tmp_path):
    c = r.load_case(_with_limits(tmp_path, timeout_s=3600, max_turns=120))
    assert (c.timeout_s, c.max_turns) == (3600, 120) == (r.MAX_CASE_TIMEOUT_S, r.MAX_CASE_TURNS)


@pytest.mark.parametrize("kw,fragment", [
    ({"timeout_s": 3601}, "timeout_s must be between 1 and 3600"),
    ({"timeout_s": 0}, "timeout_s must be between"),
    ({"max_turns": 121}, "max_turns must be between 1 and 120"),
    ({"max_turns": "lots"}, "max_turns must be an integer"),
])
def test_load_case_rejects_limits_out_of_range(tmp_path, kw, fragment):
    with pytest.raises(ValueError, match=fragment):
        r.load_case(_with_limits(tmp_path, **kw))


def test_hard_cases_use_one_hour_timeout():
    hard = [r.load_case(d) for d in sorted((r.REPO_ROOT / "evals/airflow/cases").glob("hard-*"))]
    assert len(hard) == 6
    for c in hard:
        assert c.timeout_s == 3600 and c.max_turns <= r.MAX_CASE_TURNS, c.id
    for c in r.discover_cases(r.REPO_ROOT / "evals/airflow/cases", "all"):
        assert 1 <= c.timeout_s <= r.MAX_CASE_TIMEOUT_S and 1 <= c.max_turns <= r.MAX_CASE_TURNS, c.id


@pytest.mark.parametrize("runner", ["claude-code", "altimate-code"])
def test_case_limits_reach_the_agent_command_and_watchdog(tmp_path, monkeypatch, runner):
    case = r.load_case(_with_limits(tmp_path / "cases", timeout_s=3600, max_turns=120))
    seen = {}

    def fake_process(cmd, cwd, env, events_path, stderr_path, timeout_s, cap, model, correct, spool_dir=None,
                     monitor_factory=None):
        seen.update(cmd=cmd, timeout_s=timeout_s)
        events_path.write_text("")
        stderr_path.write_text("")
        return {"returncode": 1, "timed_out": False, "cost_capped": False, "aborted": None, "wall_s": 1.0}

    monkeypatch.setattr(r, "run_agent_process", fake_process)
    monkeypatch.setattr(r.g, "agent_env_python", lambda v: str(tmp_path / "agent-env" / "bin" / "python"))
    if runner == "claude-code":
        args, model = _claude_args(tmp_path), "claude-sonnet-5-5"
    else:
        args = r.argparse.Namespace(work_dir=tmp_path / "work", keep_workspaces=False, keep_traces=False,
                                    max_run_cost_usd=None)
        args.work_dir.mkdir()
        model = "google-vertex-anthropic/claude-haiku-4-5@20251001"
    r.run_attempt(case, model, "skill", tmp_path / "out" / "attempt-0", tmp_path / "staged", set(), args, _Budget())
    cmd = seen["cmd"]
    assert cmd[cmd.index("--max-turns") + 1] == "120" and seen["timeout_s"] == 3600


def test_run_agent_process_honours_long_timeout(tmp_path):
    """The watchdog compares wall time with the case's timeout_s (no hidden lower cap)."""
    res = r.run_agent_process([sys.executable, "-c", "import time; time.sleep(3)"], tmp_path, dict(os.environ),
                              tmp_path / "e.jsonl", tmp_path / "s.log", 3600, None, "m", False)
    assert res["returncode"] == 0 and not res["timed_out"]
    short = r.run_agent_process([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, dict(os.environ),
                                tmp_path / "e2.jsonl", tmp_path / "s2.log", 1, None, "m", False)
    assert short["timed_out"] and short["wall_s"] < 25
