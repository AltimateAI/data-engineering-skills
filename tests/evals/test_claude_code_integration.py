"""Integration tests for the claude-code runner against the real ``claude`` CLI.

Slow and opt-in: they need ``EVAL_RUN_SLOW=1``, ``CLAUDE_CODE_OAUTH_TOKEN`` or
``EVAL_CLAUDE_TOKEN_CMD``, the ``claude`` binary and the 3.3 agent venv. The
inventory test makes no model call; the run test makes one short Sonnet call.
"""

import os
import shutil
import tempfile
from pathlib import Path

import claude_code as cc
import grading as g
import isolation as iso
import pytest
import run_eval as r

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(os.environ.get("EVAL_RUN_SLOW") != "1", reason="set EVAL_RUN_SLOW=1"),
    pytest.mark.skipif(not (os.environ.get(cc.TOKEN_VAR) or os.environ.get(cc.TOKEN_CMD_VAR)),
                       reason=f"needs {cc.TOKEN_VAR} or {cc.TOKEN_CMD_VAR}"),
    pytest.mark.skipif(shutil.which(cc.CLAUDE_BIN) is None, reason="claude CLI not installed"),
    pytest.mark.skipif(not Path(g.agent_env_python("3.3")).exists(), reason="agent env missing (setup_envs.sh)"),
]


@pytest.mark.parametrize("arm", ["baseline", "skill"])
def test_inventory_only_both_arms(arm, capsys):
    assert r.main(["--runner", "claude-code", "--arm", arm, "--inventory-only", "--models", "claude-sonnet-5-5"]) == 0
    out = capsys.readouterr().out
    assert '"problems": []' in out and "sk-ant-" not in out


def test_sandboxed_run_streams_bash_and_hides_host_config(tmp_path):
    work = r.work_root()
    camp = Path(tempfile.mkdtemp(prefix="cc-integration-", dir=work))
    try:
        staged = r.stage_skills("baseline", r.REPO_ROOT / "skills", r.REPO_ROOT / "skills/airflow", camp / "skills")
        flat = camp / "flat"
        repo_names = cc.flatten_skills(staged, flat)
        ctx = r.AttemptContext(out_dir=None, work_dir=camp, staged_skills=staged, runner="claude-code",
                               sandbox=iso.sandbox_available(), flat_skills=flat, arm="baseline",
                               airflow_names=r.skill_names(r.REPO_ROOT / "skills/airflow"), repo_names=repo_names)
        args = r.argparse.Namespace(work_dir=camp, ctx=ctx)

        def fixture(scratch: Path) -> Path:
            ws = scratch / "ws"
            ws.mkdir()
            r.git(ws, "init", "-q")
            return ws

        prompt = ("Use the Bash tool exactly once to run: mkdir -p sub/dir && python3 -c 'print(6*7)' && "
                  "cat ~/.claude.json | head -c 20; then reply with the number only.")
        prep = r.prepare_agent("cc-int", g.agent_env_python("3.3"), fixture, prompt, "claude-sonnet-5-5", 4,
                               staged, args)
        events_path, stderr_path = tmp_path / "events.jsonl", tmp_path / "stderr.log"
        proc = r.launch_agent(prep, ctx, "claude-sonnet-5-5", events_path, stderr_path, 300, 1.0, False)
        events = g.load_events(events_path)
        assert proc["returncode"] == 0 and not proc["aborted"] and proc["inventory_problems"] == []
        bash = g.tool_uses(events, "bash")
        assert bash and "42" in bash[0]["output"]
        if ctx.sandbox:
            assert "Operation not permitted" in bash[0]["output"]  # ~/.claude.json is denied
        assert g.usage(events, "claude-sonnet-5-5")["cost_usd_equivalent"] > 0
        assert g.termination(events)["why_harness_stopped"] == "completed"
        assert "sk-ant-" not in events_path.read_text() + stderr_path.read_text()
    finally:
        shutil.rmtree(camp, ignore_errors=True)
