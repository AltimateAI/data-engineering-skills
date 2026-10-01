"""``EVAL_CLAUDE_TOKEN_CMD``: a fresh Claude Code OAuth token per attempt from a command.
No network; the token command is a fake script that counts its calls."""

import json
import sys

import claude_code as cc
import grading as g
import pytest
import run_eval as r
from test_claude_code import AIRFLOW, FIXTURES, REPO, _Budget, assistant, classify, init, result, skill

FAKE_TOKEN = "faketoken-{n}-0123456789abcdef"


def _token_cmd(tmp_path, fail_first=False):
    """Fake token command: prints ``faketoken-<n>-...`` and counts its calls in a file."""
    script = tmp_path / "fake_token.py"
    script.write_text(
        "import pathlib, sys\n"
        "c = pathlib.Path(sys.argv[1]); n = int(c.read_text()) + 1 if c.exists() else 1; c.write_text(str(n))\n"
        f"if {fail_first!r} and n == 1:\n"
        "    print('faketoken-should-not-leak-0000'); sys.exit(2)\n"
        "print(f'faketoken-{n}-0123456789abcdef')\n")
    counter = tmp_path / "calls"
    return f"{sys.executable} {script} {counter}", counter


def test_fetch_token_runs_command_without_shell(tmp_path):
    cmd, counter = _token_cmd(tmp_path)
    assert cc.fetch_token(cmd) == FAKE_TOKEN.format(n=1)
    assert cc.fetch_token(cmd) == FAKE_TOKEN.format(n=2) and counter.read_text() == "2"
    marker = tmp_path / "pwned"
    # no shell: `;` is a plain argument to `false`, not a second command
    with pytest.raises(cc.TokenCommandError):
        cc.fetch_token(f"false ; touch {marker}")
    assert not marker.exists()


def test_fetch_token_failures_never_include_output(tmp_path):
    cmd, _ = _token_cmd(tmp_path, fail_first=True)
    with pytest.raises(cc.TokenCommandError) as exc:
        cc.fetch_token(cmd)
    assert "exited with code 2" in str(exc.value) and "faketoken" not in str(exc.value)
    for bad in ("", "   ", "'unterminated", str(tmp_path / "missing-binary")):
        with pytest.raises(cc.TokenCommandError):
            cc.fetch_token(bad)
    two_lines = tmp_path / "two.py"
    two_lines.write_text("print('a' * 20); print('b' * 20)\n")
    with pytest.raises(cc.TokenCommandError, match="single-line"):
        cc.fetch_token(f"{sys.executable} {two_lines}")


def test_agent_env_fetches_fresh_token_per_call_and_registers_it(tmp_path, monkeypatch):
    cmd, counter = _token_cmd(tmp_path)
    monkeypatch.setenv(cc.TOKEN_CMD_VAR, cmd)
    base = {"PATH": "/usr/bin", "TMPDIR": str(tmp_path / "tmp"), cc.TOKEN_VAR: "stale-token-from-env",
            cc.TOKEN_CMD_VAR: cmd}
    e1 = cc.agent_env(base, tmp_path / "cfg")
    e2 = cc.agent_env(base, tmp_path / "cfg")
    assert e1[cc.TOKEN_VAR] == FAKE_TOKEN.format(n=1) and e2[cc.TOKEN_VAR] == FAKE_TOKEN.format(n=2)
    assert cc.TOKEN_CMD_VAR not in e1 and counter.read_text() == "2"
    # not an sk-ant-* value, so it is redacted as a registered literal
    assert r.san.redact_secrets(f"x {FAKE_TOKEN.format(n=1)} y") == f"x {r.san.REDACTED} y"
    monkeypatch.delenv(cc.TOKEN_CMD_VAR)
    assert cc.agent_env(base, tmp_path / "cfg")[cc.TOKEN_VAR] == "stale-token-from-env"


def test_sanitize_pattern_covers_oauth_access_tokens():
    tok = "sk-ant-oat01-" + "Ab3_-" * 19  # shape of a Claude Code OAuth access token
    assert r.san.redact_secrets(f'{{"accessToken":"{tok}"}}') == f'{{"accessToken":"{r.san.REDACTED}"}}'


def test_build_agent_env_drops_token_command(tmp_path, monkeypatch):
    monkeypatch.setenv(cc.TOKEN_CMD_VAR, "echo x")
    env = r.build_agent_env(tmp_path / "a", tmp_path / "ws", tmp_path / "skills", str(tmp_path / "venv" / "bin" / "python"))
    assert cc.TOKEN_CMD_VAR not in env


def test_require_claude_token_accepts_token_command(tmp_path, monkeypatch):
    monkeypatch.delenv(cc.TOKEN_VAR, raising=False)
    monkeypatch.delenv(cc.TOKEN_CMD_VAR, raising=False)
    with pytest.raises(SystemExit):
        r.require_claude_token()
    cmd, counter = _token_cmd(tmp_path)
    monkeypatch.setenv(cc.TOKEN_CMD_VAR, cmd)
    r.require_claude_token()
    assert counter.read_text() == "1"
    monkeypatch.setenv(cc.TOKEN_CMD_VAR, "false")
    with pytest.raises(SystemExit) as exc:
        r.require_claude_token()
    assert cc.TOKEN_CMD_VAR in str(exc.value)


def test_expired_token_mid_run_is_retryable_infra_error():
    ev = [init([]), assistant("m1", {"type": "text", "text": "working"}),
          result(is_error=True, text='Failed to authenticate. API Error: 401 {"type":"error","error":'
                                     '{"type":"authentication_error","message":"OAuth token has expired."}}')]
    status, reason = classify(ev)
    assert status == "infra_error"
    rec = {"status": status, "reason": reason, "errors": g.error_messages(ev)}
    assert r.should_retry(rec) and not cc.is_usage_limit(rec)


def test_token_command_failure_is_infra_error_and_retry_gets_fresh_token(tmp_path, monkeypatch):
    from test_run_eval import make_case

    case = r.load_case(make_case(tmp_path / "cases", "c1"))
    cmd, counter = _token_cmd(tmp_path, fail_first=True)
    monkeypatch.setenv(cc.TOKEN_CMD_VAR, cmd)
    monkeypatch.delenv(cc.TOKEN_VAR, raising=False)
    recorded = (FIXTURES / "claude_stream_skill_run.jsonl").read_text()
    tokens = []

    def fake_process(cmd, cwd, env, events_path, stderr_path, timeout_s, cap, model, correct, spool_dir=None,
                     monitor_factory=None):
        tokens.append(env.get(cc.TOKEN_VAR))
        assert cc.TOKEN_CMD_VAR not in env
        # an agent that echoes its token: it must not survive into any artifact
        events_path.write_text(recorded + json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "x", "content": f"tok={env.get(cc.TOKEN_VAR)}"}]}}) + "\n")
        r.san.redact_file(events_path)
        stderr_path.write_text(f"debug {env.get(cc.TOKEN_VAR)}\n")
        r.san.redact_file(stderr_path)
        mon = monitor_factory(events_path)
        mon.poll()
        return {"returncode": 0, "timed_out": False, "cost_capped": False, "aborted": mon.abort_reason,
                "wall_s": 3.0, "inventory": mon.inventory, "inventory_problems": mon.inventory_problems}

    monkeypatch.setattr(r, "run_agent_process", fake_process)
    monkeypatch.setattr(r.g, "agent_env_python", lambda v: str(tmp_path / "agent-env" / "bin" / "python"))
    monkeypatch.setattr(r, "run_grader", lambda *a, **k: ({"primary_pass": True, "checks": [], "primary_score": 1.0,
                                                           "secondary_score": None}, False))
    flat = tmp_path / "flat"
    for n in REPO + AIRFLOW:
        skill(flat, n, n)
    args = r.argparse.Namespace(work_dir=tmp_path / "work", keep_workspaces=False, keep_traces=False,
                                max_run_cost_usd=None)
    args.work_dir.mkdir()
    args.ctx = r.AttemptContext(out_dir=None, work_dir=args.work_dir, staged_skills=tmp_path / "staged",
                                runner="claude-code", flat_skills=flat, arm="skill", airflow_names=AIRFLOW,
                                repo_names=REPO, usage_gate=cc.UsageLimitGate())
    run_dir = tmp_path / "out" / "run-1"
    row, slept = {"attempts": []}, []
    r.attempt_loop(row, lambda k: r.run_attempt(case, "claude-sonnet-5-5", "skill", run_dir / f"attempt-{k}",
                                                tmp_path / "staged", set(AIRFLOW), args, _Budget()),
                   args.ctx, _Budget(), "c1 m run-1", sleep=slept.append)
    assert [a["status"] for a in row["attempts"]] == ["infra_error", "ok"] and slept == [30]
    first = row["attempts"][0]
    assert first["reason"].startswith("token command failed") and not first["launched"]
    assert tokens == [FAKE_TOKEN.format(n=2)] and counter.read_text() == "2"
    assert list(args.work_dir.iterdir()) == []  # the failed attempt's scratch dir is removed
    for f in run_dir.rglob("*"):
        if f.is_file():
            assert "faketoken" not in f.read_text(errors="replace"), f
