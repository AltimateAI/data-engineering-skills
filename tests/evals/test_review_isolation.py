"""Regressions for PR 18's independent harness-isolation review."""

import concurrent.futures
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import grading as g
import isolation as iso
import pytest
import run_eval as r
import run_triggers as triggers
from test_isolation import make_roots
from test_run_eval import STEP, make_case


def test_policy_denies_checkout_and_earlier_campaigns(tmp_path, monkeypatch):
    roots = make_roots(tmp_path)
    cache = Path(roots.base["HOME"]) / ".cache/des-evals"
    monkeypatch.setenv("EVAL_ENV_ROOT", str(tmp_path / "custom-envs"))
    prior = roots.out_dir.parent / "earlier-output"
    prior.mkdir()
    (prior / "meta.json").write_text("{}")
    for path in (r.REPO_ROOT / "evals/airflow/cases/x/reference/dags/x.py",
                 r.REPO_ROOT / "evals/airflow/results/another/agent.patch",
                 cache / "prior-campaign/agent.patch",
                 tmp_path / "custom-envs/prior-campaign/agent.patch",
                 roots.out_dir.parent / "earlier-output/agent.patch"):
        result = iso.scan_contamination([{"tool": "read", "input": {"filePath": str(path)}}], roots.policy())
        assert result["contamination_suspect"], path
    assert iso.classify_path(str(roots.agent_venv / "lib/package.py"), roots.policy()) is None


@pytest.mark.skipif(not iso.sandbox_available(), reason="sandbox-exec unavailable")
@pytest.mark.parametrize("runner", ["claude-code", "altimate-code"])
def test_sandbox_denies_checkout_and_prior_results(tmp_path, monkeypatch, runner):
    roots = make_roots(tmp_path)
    roots.runner = runner
    monkeypatch.setenv("EVAL_ENV_ROOT", str(tmp_path / "envs"))
    old = Path(roots.base["HOME"]) / ".cache/des-evals/old/agent.patch"
    old.parent.mkdir(parents=True)
    old.write_text("earlier answer")
    profile = roots.scratch / "sandbox.sb"
    profile.write_text(roots.sandbox_profile())
    targets = [old, r.REPO_ROOT / "evals/airflow/cases", r.REPO_ROOT / "evals/airflow/results"]
    for target in targets:
        result = subprocess.run(iso.sandbox_wrap(["/bin/ls", str(target)], profile),
                                capture_output=True, text=True)
        assert result.returncode != 0 and "Operation not permitted" in result.stderr
    result = subprocess.run(iso.sandbox_wrap([sys.executable, "-c", "print('runtime works')"], profile),
                            capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.strip() == "runtime works", result.stderr


@pytest.mark.skipif(not iso.sandbox_available() or not shutil.which("codesign"),
                    reason="requires macOS sandbox and codesign")
@pytest.mark.parametrize("runner", ["claude-code", "altimate-code"])
def test_sandbox_hides_outside_argv_and_known_pid(tmp_path, runner):
    roots = make_roots(tmp_path)
    roots.runner = runner
    profile = roots.scratch / "sandbox.sb"
    profile.write_text(roots.sandbox_profile())
    # /bin/ps is setuid on macOS and cannot execute under sandbox-exec. Use an
    # unprivileged ad-hoc signed copy so failure to launch cannot mask a leak.
    ps = roots.scratch / "ps"
    shutil.copyfile(shutil.which("ps"), ps)
    ps.chmod(0o755)
    subprocess.run(["codesign", "--force", "--sign", "-", str(ps)], check=True, capture_output=True)
    tag = f"des-private-argv-{os.getpid()}-{runner}"
    outside = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", tag])
    try:
        control = subprocess.run([str(ps), "aux"], capture_output=True, text=True, check=True)
        assert tag in control.stdout
        result = subprocess.run(iso.sandbox_wrap([str(ps), "aux"], profile), capture_output=True, text=True)
        assert tag not in result.stdout
        assert "Operation not permitted" in result.stderr
        # Enumeration denial must also cover an attacker who already knows a PID.
        code = (
            "import ctypes,json; lib=ctypes.CDLL(None,use_errno=True); "
            f"mib=(ctypes.c_int*3)(1,49,{outside.pid}); "
            "buf=ctypes.create_string_buffer(65536); n=ctypes.c_size_t(len(buf)); "
            "rc=lib.sysctl(mib,3,buf,ctypes.byref(n),None,0); "
            "print(json.dumps([rc,ctypes.get_errno(),buf.raw.decode(errors='replace')]))"
        )
        result = subprocess.run(iso.sandbox_wrap([sys.executable, "-c", code], profile),
                                cwd=roots.scratch, capture_output=True, text=True, check=True)
        rc, error, contents = json.loads(result.stdout)
        assert (rc, error) == (-1, 1) and tag not in contents
    finally:
        outside.terminate()
        outside.wait(timeout=10)


@pytest.mark.skipif(not iso.sandbox_available(), reason="sandbox-exec unavailable")
@pytest.mark.parametrize("runner,command", [("claude-code", ["claude", "--version"]),
                                           ("altimate-code", ["altimate-code", "--version"]),
                                           ("altimate-code", ["altimate-code", "skill", "list", "--json"])])
def test_sandbox_runner_local_startup(tmp_path, runner, command):
    executable = shutil.which(command[0])
    if executable is None:
        pytest.skip(f"{command[0]} is not installed")
    roots = make_roots(tmp_path)
    roots.runner, roots.base = runner, dict(os.environ)
    ws = roots.scratch / "ws"
    ws.mkdir()
    env = r.build_agent_env(roots.scratch, ws, roots.staged_skills, str(roots.agent_venv / "bin/python"))
    env["CLAUDE_CONFIG_DIR"] = str(roots.scratch / "claude-config")
    Path(env["CLAUDE_CONFIG_DIR"]).mkdir()
    profile = roots.scratch / "sandbox.sb"
    profile.write_text(roots.sandbox_profile())
    result = subprocess.run(iso.sandbox_wrap([executable, *command[1:]], profile),
                            env=env, cwd=ws, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


@pytest.mark.parametrize("kind", ["final-symlink", "trace-path", "link-cycle"])
def test_attempt_artifact_refuses_external_or_cyclic_path(tmp_path, kind):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    secret = tmp_path / "secret"
    secret.write_text("outside")
    path = scratch / "final.md"
    if kind == "final-symlink":
        path.symlink_to(secret)
    elif kind == "trace-path":
        path = secret
    else:
        path.symlink_to(path)
    with pytest.raises(g.UnsafeWorkspaceError):
        r.attempt_artifact(path, scratch)
    (scratch / "safe.md").write_text("safe")
    assert r.attempt_artifact(scratch / "safe.md", scratch).read_text() == "safe"


def test_claude_final_answer_does_not_follow_dangling_symlink(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    outside = tmp_path / "outside.md"
    (scratch / "final.md").symlink_to(outside)
    with pytest.raises(g.UnsafeWorkspaceError, match="outside scratch"):
        r.runner_fields(r.argparse.Namespace(runner="claude-code"),
                        [{"type": "result", "result": "answer"}], {"cost_usd": 0}, {}, scratch)
    assert not outside.exists()


@pytest.mark.parametrize("timeout", [False, True])
def test_agent_group_cleanup_kills_real_grandchild(tmp_path, monkeypatch, timeout):
    heartbeat, ready = tmp_path / "heartbeat", tmp_path / "ready"
    grandchild = (
        "import os,signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"pathlib.Path({str(ready)!r}).write_text(str(os.getpid())); "
        f"f=open({str(heartbeat)!r},'a');\n"
        "while True:\n f.write('x'); f.flush(); time.sleep(.02)\n"
    )
    child = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{grandchild!r}]); time.sleep(60)"
    leader = (f"import subprocess,sys,time,pathlib; subprocess.Popen([sys.executable,'-c',{child!r}]);\n"
              f"while not pathlib.Path({str(ready)!r}).exists(): time.sleep(.01)\n"
              + ("time.sleep(60)\n" if timeout else ""))
    original = r.stop_process_group
    monkeypatch.setattr(r, "stop_process_group", lambda proc, grace_s=15: original(proc, grace_s=.2))
    pid = None
    try:
        result = r.run_agent_process([sys.executable, "-c", leader], tmp_path, dict(os.environ),
                                     tmp_path / "events", tmp_path / "stderr", 3 if timeout else 20,
                                     None, "m", False)
        pid = int(ready.read_text())
        assert result["timed_out"] is timeout
        if not timeout:
            assert result["returncode"] == 0
        time.sleep(.1)
        stopped_at = heartbeat.stat().st_size
        time.sleep(.15)
        assert heartbeat.stat().st_size == stopped_at
        status = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
        assert not status.stdout.strip() or status.stdout.strip().startswith("Z"), status.stdout
    finally:
        if pid is None and ready.exists():
            pid = int(ready.read_text())
        if pid is not None:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize("kind", ["external-file", "external-directory", "loop", "directory-cycle"])
def test_copy_workspace_refuses_unsafe_symlinks(tmp_path, kind):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "reference.py"
    outside.write_text("hidden solution")
    link = ws / "x.py"
    link.symlink_to({"external-file": outside, "external-directory": tmp_path,
                     "loop": link, "directory-cycle": ws}[kind])
    dest = tmp_path / "grade-ws"
    with pytest.raises(g.UnsafeWorkspaceError, match="unsafe workspace symlinks"):
        g.copy_workspace(ws, dest=dest)
    assert not dest.exists()


def test_copy_workspace_rebases_internal_file_symlinks(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "original.py").write_text("local implementation")
    (ws / "absolute.py").symlink_to(ws / "original.py")
    (ws / "relative.py").symlink_to("original.py")
    dest = g.copy_workspace(ws, dest=tmp_path / "copy")
    shutil.rmtree(ws)
    assert (dest / "absolute.py").read_text() == (dest / "relative.py").read_text() == "local implementation"


def test_copy_workspace_default_temp_alias_is_safe(tmp_path, monkeypatch):
    source, real_temp, alias = tmp_path / "ws", tmp_path / "real-temp", tmp_path / "alias"
    source.mkdir()
    (source / "a.py").write_text("local")
    real_temp.mkdir()
    alias.symlink_to(real_temp, target_is_directory=True)
    monkeypatch.setattr(g.tempfile, "tempdir", str(alias))
    copy = g.copy_workspace(source)
    assert copy.is_relative_to(real_temp)
    assert (copy / "a.py").read_text() == "local"


@pytest.mark.parametrize("kind", ["source-root", "destination", "destination-ancestor"])
def test_copy_workspace_refuses_planted_root_or_destination(tmp_path, kind):
    ws, outside = tmp_path / "ws", tmp_path / "outside"
    ws.mkdir()
    outside.mkdir()
    (outside / "solution.py").write_text("hidden")
    (ws / "agent.py").write_text("agent data")
    dest = tmp_path / "grade-ws"
    if kind == "source-root":
        shutil.rmtree(ws)
        ws.symlink_to(outside, target_is_directory=True)
    elif kind == "destination":
        dest.symlink_to(outside, target_is_directory=True)
    else:
        (tmp_path / "alias").symlink_to(outside, target_is_directory=True)
        dest = tmp_path / "alias" / "grade-ws"
    with pytest.raises(g.UnsafeWorkspaceError):
        g.copy_workspace(ws, dest=dest)
    assert not (outside / "agent.py").exists()
    assert not (outside / "grade-ws").exists()


@pytest.mark.parametrize("kind", ["external", "loop"])
def test_unsafe_agent_workspace_is_task_fail_not_harness_error(tmp_path, monkeypatch, kind):
    case = r.load_case(make_case(tmp_path / "cases", "case"))
    args = r.argparse.Namespace(work_dir=tmp_path / "work", keep_workspaces=False, keep_traces=False,
                                max_run_cost_usd=None)
    args.work_dir.mkdir()
    monkeypatch.setattr(g, "agent_env_python", lambda _: str(tmp_path / "venv/bin/python"))

    def launch(prep, ctx, model, events, stderr, *args):
        link = prep["ws"] / "dags/x.py"
        link.symlink_to(case.fixture / "dags/a.py" if kind == "external" else link)
        events.write_text(json.dumps(STEP) + "\n")
        stderr.write_text("")
        return {"returncode": 0, "wall_s": 0, "timed_out": False, "cost_capped": False}

    monkeypatch.setattr(r, "launch_agent", launch)
    monkeypatch.setattr(r, "run_grader", lambda *a, **k: pytest.fail("unsafe workspace reached grader"))
    result = r.run_attempt(case, "m", "skill", tmp_path / "out", tmp_path / "skills", set(), args, r.Budget(10))
    assert result["status"] == "task_fail" and result["primary_score"] == 0
    assert result["contamination_suspect"] and "unsafe workspace symlinks" in result["reason"]


@pytest.mark.parametrize("separate_guard", [False, True])
def test_env_guard_waits_for_active_attempt(tmp_path, separate_guard):
    venv = tmp_path / "venv"
    venv.mkdir()
    guard = iso.AgentEnvGuard(venv)
    other = iso.AgentEnvGuard(venv) if separate_guard else guard
    entered = threading.Event()
    extra = venv / "package_installed_by_agent.py"

    def check():
        entered.set()
        return other.check()

    with concurrent.futures.ThreadPoolExecutor() as pool:
        with guard.attempt():
            extra.write_text("needed by the active attempt")
            future = pool.submit(check)
            assert entered.wait(5)
            time.sleep(.1)
            assert not future.done() and extra.exists()
            assert guard.check()["restored"]  # reentrant post-check by the owner
        assert future.result(timeout=5)["changed"] is False
    assert not extra.exists()


def test_env_guard_lease_blocks_other_harness_process(tmp_path):
    venv = tmp_path / "venv"
    venv.mkdir()
    iso.write_pristine(venv)
    guard = iso.AgentEnvGuard(venv)
    started, done = tmp_path / "started", tmp_path / "done"
    extra = venv / "installed.py"
    code = (f"import sys,pathlib; sys.path.insert(0,{str(r.HARNESS_DIR)!r}); import isolation; "
            f"pathlib.Path({str(started)!r}).touch(); g=isolation.AgentEnvGuard({str(venv)!r}); "
            f"g.check(); pathlib.Path({str(done)!r}).touch()")
    child = None
    try:
        with guard.attempt():
            extra.write_text("in use")
            child = subprocess.Popen([sys.executable, "-c", code])
            deadline = time.monotonic() + 5
            while not started.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            assert started.exists()
            time.sleep(.1)
            assert extra.exists() and not done.exists()
        assert child.wait(timeout=10) == 0
        assert done.exists() and not extra.exists()
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()


def test_env_guard_initial_snapshot_waits_for_active_attempt(tmp_path):
    venv = tmp_path / "venv"
    venv.mkdir()
    guard = iso.AgentEnvGuard(venv)
    started = threading.Event()
    extra = venv / "installed.py"

    def construct():
        started.set()
        return iso.AgentEnvGuard(venv)

    with concurrent.futures.ThreadPoolExecutor() as pool:
        with guard.attempt():
            extra.write_text("in use")
            future = pool.submit(construct)
            assert started.wait(5)
            time.sleep(.1)
            assert not future.done()
            assert guard.check()["restored"]
        other = future.result(timeout=5)
    assert other.pristine == guard.pristine and not other.check()["changed"]


@pytest.mark.parametrize("entry", ["task", "trigger"])
def test_attempt_holds_env_lease_during_agent_execution(tmp_path, monkeypatch, entry):
    case = r.load_case(make_case(tmp_path / "cases", "case"))
    venv = tmp_path / "venv"
    venv.mkdir()
    guard = iso.AgentEnvGuard(venv)
    args = r.argparse.Namespace(work_dir=tmp_path / "work", keep_workspaces=False, keep_traces=False,
                                max_run_cost_usd=None, max_turns=1, timeout_s=10)
    args.work_dir.mkdir()
    args.ctx = r.AttemptContext(None, args.work_dir, tmp_path / "skills", env_guards={"3.3": guard})
    monkeypatch.setattr(g, "agent_env_python", lambda _: str(venv / "bin/python"))
    release, active, checking = threading.Event(), threading.Event(), threading.Event()
    extra = venv / "installed.py"

    def launch(prep, ctx, model, events, stderr, *args):
        extra.write_text("needed by the agent")
        active.set()
        assert release.wait(5)
        assert extra.exists()
        events.write_text(json.dumps(STEP) + "\n")
        stderr.write_text("")
        return {"returncode": 0, "wall_s": 0, "timed_out": False, "cost_capped": False}

    def check():
        checking.set()
        return guard.check()

    monkeypatch.setattr(r, "launch_agent", launch)
    monkeypatch.setattr(r, "run_grader", lambda *a, **k: ({"primary_pass": True, "checks": []}, False))
    if entry == "task":
        run = lambda: r.run_attempt(case, "m", "skill", tmp_path / "out", tmp_path / "skills", set(),
                                    args, r.Budget(10))
    else:
        run = lambda: triggers.run_attempt({"id": "q", "query": "q"},
                                           {"airflow_version": "3.3", "fixture": case.fixture}, "m",
                                           tmp_path / "out", tmp_path / "skills", args, r.Budget(10))
    with concurrent.futures.ThreadPoolExecutor() as pool:
        attempt = pool.submit(run)
        try:
            assert active.wait(5)
            checker = pool.submit(check)
            assert checking.wait(5)
            time.sleep(.1)
            assert not checker.done() and extra.exists()
        finally:
            release.set()
        result = attempt.result(timeout=10)
        assert result["status"] in {"ok", "ran"}, result
        assert result["agent_env_post"]["changed"] and result["agent_env_post"]["restored"]
        assert checker.result(timeout=5)["changed"] is False
