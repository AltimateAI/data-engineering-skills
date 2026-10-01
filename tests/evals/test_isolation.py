"""Unit tests for evals/harness/isolation.py and the isolation pieces of run_eval.py."""

import os
import subprocess
import sys
from pathlib import Path

import isolation as iso
import pytest
import run_eval as r


def tool(name, output="", **inp):
    return {"tool": name, "input": inp, "output": output}


def policy(tmp_path):
    scratch = tmp_path / "work" / "run-1" / "case-abc"
    return iso.ContaminationPolicy(
        forbidden=[("shared-temp", "/tmp"), ("shared-temp", "/private/tmp"), ("repo", str(tmp_path / "repo")),
                   ("work-root", str(tmp_path / "work"))],
        allowed=[str(scratch), str(tmp_path / "work" / "run-1" / "skills")],
        home=str(tmp_path / "home"),
    ), scratch


def test_paths_in_text():
    cmd = "cd /a/b && python x.py --out=/tmp/x.json; cat ~/f | grep y > rel/z 'q/r' \"/c d\""
    assert iso.paths_in_text(cmd) == ["/a/b", "/tmp/x.json", "~/f", "/c"]


def test_classify_path(tmp_path):
    pol, scratch = policy(tmp_path)
    assert iso.classify_path("/tmp/carrier_scorecard.json", pol) == "shared-temp"
    assert iso.classify_path(str(tmp_path / "repo/evals/airflow/cases/x/grade.py"), pol) == "repo"
    assert iso.classify_path(str(tmp_path / "work/run-1/other-case/ws/dags/a.py"), pol) == "work-root"
    assert iso.classify_path(str(scratch / "ws/dags/a.py"), pol) is None
    assert iso.classify_path(str(scratch / "tmp/airflow-check-db-1"), pol) is None
    assert iso.classify_path(str(tmp_path / "work/run-1/skills/airflow/x/SKILL.md"), pol) is None
    assert iso.classify_path("/usr/bin/env", pol) is None
    assert iso.classify_path("/tmpfoo/x", pol) is None  # prefix match is per path component


def test_scan_contamination_flags_and_denied(tmp_path):
    pol, scratch = policy(tmp_path)
    calls = [
        tool("bash", command=f"cd {scratch}/ws && cat /tmp/hourly_pageviews_before.json", output="{...}"),
        tool("read", filePath=str(tmp_path / "repo/evals/airflow/cases/a/reference/dags/x.py")),
        tool("bash", command="touch /tmp/probe", output="touch: /tmp/probe: Operation not permitted"),
        tool("write", filePath=str(scratch / "ws/dags/a.py"), content="open('/tmp/not-a-path-ref')"),
        tool("glob", pattern="**/*.py", path=str(scratch / "ws")),
    ]
    res = iso.scan_contamination(calls, pol)
    assert res["contamination_suspect"] is True
    assert [(h["call"], h["root"]) for h in res["hits"]] == [(0, "shared-temp"), (1, "repo")]
    assert [(h["call"], h["path"]) for h in res["denied_hits"]] == [(2, "/tmp/probe")]
    clean = iso.scan_contamination(calls[3:], pol)
    assert clean == {"contamination_suspect": False, "hits": [], "denied_hits": []}


def test_sandbox_profile_text(tmp_path):
    prof = iso.sandbox_profile(write_allow=[tmp_path / "s", "/dev"], read_deny=[tmp_path / "repo"],
                               read_allow=[tmp_path / "s"], read_allow_literal=[tmp_path / "auth.json"])
    lines = prof.splitlines()
    assert lines[:3] == ["(version 1)", "(allow default)", "(deny file-write*)"]
    real = os.path.realpath(tmp_path)
    assert f'(subpath "{real}/s")' in lines[3] and '(subpath "/dev")' in lines[3]
    assert lines[4] == f'(deny file-read* (subpath "{real}/repo"))'
    assert lines[5] == f'(allow file-read* (subpath "{real}/s") (literal "{real}/auth.json"))'
    assert iso._sbpl_str('a"b\\c') == '"a\\"b\\\\c"'


def make_roots(tmp_path):
    scratch = tmp_path / "work" / "camp" / "case-x"
    for d in (scratch / "tmp", tmp_path / "work" / "camp" / "skills", tmp_path / "work" / "camp" / "other",
              tmp_path / "venv" / "bin", tmp_path / "out"):
        d.mkdir(parents=True, exist_ok=True)
    (tmp_path / "work" / "camp" / "other" / "secret.txt").write_text("other attempt")
    (tmp_path / "out" / "events.jsonl").write_text("{}")
    return r.IsolationRoots(scratch=scratch, agent_venv=tmp_path / "venv",
                            staged_skills=tmp_path / "work" / "camp" / "skills", out_dir=tmp_path / "out",
                            work_root=tmp_path / "work", base={"HOME": str(tmp_path / "home")})


def test_isolation_roots_policy(tmp_path):
    roots = make_roots(tmp_path)
    labels = {label for label, _ in roots.forbidden()}
    assert {"shared-temp", "repo", "results", "work-root", "altimate-data", "user-skills", "grader-env"} <= labels
    pol = roots.policy()
    assert iso.classify_path(str(roots.scratch / "ws/a.py"), pol) is None
    assert iso.classify_path(str(tmp_path / "work/camp/other/secret.txt"), pol) == "work-root"
    assert iso.classify_path(str(tmp_path / "out/events.jsonl"), pol) == "results"
    assert iso.classify_path(str(r.REPO_ROOT / "evals/airflow/cases"), pol) == "repo"
    assert iso.classify_path("~/.claude/skills/x/SKILL.md", pol) == "user-skills"


@pytest.mark.skipif(not iso.sandbox_available(), reason="sandbox-exec not available")
def test_sandbox_enforces_profile(tmp_path):
    """Real sandbox-exec: writes only in scratch, no reads of the repo, other attempts or results."""
    roots = make_roots(tmp_path)
    prof = tmp_path / "p.sb"
    prof.write_text(roots.sandbox_profile())
    s = roots.scratch

    def sh(cmd):
        return subprocess.run(iso.sandbox_wrap(["/bin/sh", "-c", cmd], prof), capture_output=True, text=True)

    assert sh(f"echo ok > {s}/tmp/a && cat {s}/tmp/a").stdout.strip() == "ok"
    assert sh(f"echo ok > {tmp_path}/venv/bin/x").returncode == 0  # agent venv stays writable
    assert sh("echo x > /private/tmp/des-evals-sandbox-probe").returncode != 0
    assert sh(f"echo x > {tmp_path}/out/new").returncode != 0
    assert sh(f"cat {tmp_path}/work/camp/other/secret.txt").returncode != 0
    assert sh(f"cat {tmp_path}/out/events.jsonl").returncode != 0
    assert sh(f"ls {r.REPO_ROOT}/evals").returncode != 0
    assert sh(f"ls {tmp_path}/work/camp/skills").returncode == 0
    assert sh(f"{sys.executable} -c 'print(1)'").stdout.strip() == "1"


@pytest.mark.skipif(not iso.sandbox_available() or not r.shutil.which("node"), reason="needs sandbox-exec and node")
def test_sandboxed_node_with_results_dir_denied(tmp_path):
    """node aborts at startup when its stdout is a file it cannot read, so agent stdio is
    spooled in the scratch dir and copied to the (read-denied) results dir afterwards."""
    roots = make_roots(tmp_path)
    prof = roots.scratch / "p.sb"
    prof.write_text(roots.sandbox_profile())
    step = '{"type": "step_finish", "part": {"cost": 0.25, "tokens": {}}}'
    cmd = iso.sandbox_wrap(["node", "-e", f"console.log({step!r})"], prof)
    events, stderr = tmp_path / "out" / "events.jsonl", tmp_path / "out" / "stderr.log"
    res = r.run_agent_process(cmd, roots.scratch, dict(os.environ), events, stderr, 60, None, "m", False,
                              spool_dir=roots.scratch)
    assert res["returncode"] == 0 and not res["timed_out"]
    assert '"step_finish"' in events.read_text() and stderr.read_text() == ""


def test_run_agent_process_cost_cap_stops_group(tmp_path):
    step = '{"type": "step_finish", "part": {"cost": 1.0, "tokens": {}}}'
    script = f"import time\nfor _ in range(30):\n    print({step!r}, flush=True)\n    time.sleep(0.5)\n"
    res = r.run_agent_process([sys.executable, "-c", script], tmp_path, dict(os.environ), tmp_path / "e.jsonl",
                              tmp_path / "s.log", 60, 1.5, "m", False, spool_dir=None)
    assert res["cost_capped"] and not res["timed_out"] and res["wall_s"] < 20


def test_venv_manifest_and_fingerprint(tmp_path):
    v = tmp_path / "venv"
    (v / "lib" / "__pycache__").mkdir(parents=True)
    (v / "lib" / "a.py").write_text("x")
    (v / "bin").mkdir()
    (v / "bin" / "python").symlink_to("/usr/bin/python3")
    fp = iso.venv_fingerprint(v)
    assert set(iso.venv_manifest(v)) == {"lib/a.py", "bin/python"}
    (v / "lib" / "a.py").write_text("y")  # same length, different content
    assert iso.venv_fingerprint(v) != fp
    (v / "lib" / "a.py").write_text("x")
    assert iso.venv_fingerprint(v) == fp
    (v / "lib" / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"poisoned")  # planted bytecode counts
    assert iso.venv_fingerprint(v) != fp
    assert iso.venv_fingerprint(tmp_path / "nope") == "missing"


def test_agent_env_guard_removes_extras_and_resyncs(tmp_path, monkeypatch):
    v = tmp_path / "venv"
    (v / "lib").mkdir(parents=True)
    (v / "lib" / "pkg.py").write_text("orig")
    assert iso.write_pristine(v) == iso.venv_fingerprint(v)
    iso.freeze_file(v).write_text("pkg==1\n")
    monkeypatch.setattr(iso.shutil, "which", lambda name: "/usr/bin/uv")
    calls = []

    def fake_resync(venv, reinstall=False):
        calls.append(reinstall)
        if reinstall:
            (venv / "lib" / "pkg.py").write_text("orig")
        return subprocess.CompletedProcess([], 0)

    guard = iso.AgentEnvGuard(v, resync=fake_resync)
    assert guard.check() == {"changed": False, "restored": False, "detail": ""}
    (v / "lib" / "extra").mkdir()
    (v / "lib" / "extra" / "mod.py").write_text("planted")
    res = guard.check()
    assert res["changed"] and res["restored"] and "removed 1 extra file" in res["detail"]
    assert not (v / "lib" / "extra").exists() and calls == [False]
    (v / "lib" / "pkg.py").write_text("ORIG")  # same size, edited content: needs a reinstall
    res = guard.check()
    assert res["restored"] and calls == [False, False, True] and guard.restores == 2


def test_agent_env_guard_reports_failed_restore(tmp_path):
    v = tmp_path / "venv"
    (v / "lib").mkdir(parents=True)
    (v / "lib" / "pkg.py").write_text("orig")
    iso.write_pristine(v)
    (v / "lib" / "pkg.py").write_text("edited!")  # no freeze file: cannot resync
    res = iso.AgentEnvGuard(v).check()
    assert res["changed"] and not res["restored"] and "requirements.txt" in res["detail"]


def test_build_agent_env_tmp_pip_and_path(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_ENV_ROOT", str(tmp_path / "envs"))
    grader_bin = str(tmp_path / "envs" / "airflow-3.3" / "bin")
    data = tmp_path / "home" / ".local" / "share" / "altimate-code"
    (data / "bin").mkdir(parents=True)
    (data / "auth.json").write_text("{}")
    host = {"PATH": f"{grader_bin}:/old/venv/bin:/usr/bin", "HOME": str(tmp_path / "home"), "VIRTUAL_ENV": "/old/venv",
            "TMPDIR": "/private/tmp/shared", "PYTHONUSERBASE": "/x", "PIP_USER": "1"}
    att = tmp_path / "att"
    env = r.build_agent_env(att, tmp_path / "ws", tmp_path / "skills",
                            str(tmp_path / "envs" / "agent-airflow-3.3" / "bin" / "python"), base=host)
    for k in ("TMPDIR", "TMP", "TEMP"):
        assert env[k] == str(att / "tmp")
    assert Path(env["TMPDIR"]).is_dir()
    assert env["PIP_REQUIRE_VIRTUALENV"] == "1" and "PIP_USER" not in env
    assert env["PYTHONUSERBASE"] == str(att / "agent-pyuser")
    assert env["PATH"].split(":") == [str(tmp_path / "envs" / "agent-airflow-3.3" / "bin"), "/usr/bin"]
    assert env["XDG_DATA_HOME"] == str(att / "agent-xdg-data")
    linked = att / "agent-xdg-data" / "altimate-code"
    assert (linked / "auth.json").is_symlink() and (linked / "bin").is_symlink()
    assert not (linked / "engine").exists()
    with pytest.raises(ValueError, match="grader env"):
        r.build_agent_env(att, tmp_path / "ws", tmp_path / "skills", grader_bin + "/python", base=host)
