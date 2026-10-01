"""Unit tests for the claude-code runner: stream-json parsing, classification, inventory,
usage-limit handling and resume. No network: fixtures are recorded Claude Code 2.1.286
streams (paths sanitized), plus constructed error lines in its message formats."""

import json
import os
from pathlib import Path

import claude_code as cc
import grading as g
import pytest
import run_eval as r

FIXTURES = Path(__file__).parent / "fixtures"
REPO = ["altimate-code", "creating-dbt-models", "debugging-dbt-errors", "developing-incremental-models",
        "documenting-dbt-models", "finding-expensive-queries", "migrating-sql-to-dbt", "optimizing-databricks-sql",
        "optimizing-query-by-id", "optimizing-query-text", "refactoring-dbt-models", "testing-dbt-models"]
AIRFLOW = ["authoring-airflow-dags", "migrating-to-airflow-3", "testing-airflow-dags"]


def stream(name="claude_stream_skill_run.jsonl"):
    return g.load_events(FIXTURES / name)


def init(skills, **kw):
    return {"type": "system", "subtype": "init", "skills": skills, "plugins": [], "mcp_servers": [], **kw}


def assistant(mid, block, model="claude-sonnet-5-5", usage=None, **kw):
    return {"type": "assistant", "message": {"id": mid, "model": model, "role": "assistant", "content": [block],
                                             "usage": usage or {"input_tokens": 1, "output_tokens": 1}}, **kw}


def result(subtype="success", is_error=False, cost=0.5, turns=3, text="done", **kw):
    return {"type": "result", "subtype": subtype, "is_error": is_error, "total_cost_usd": cost, "num_turns": turns,
            "result": text, "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 300,
                      "cache_creation_input_tokens": 40}, **kw}


# --------------------------------------------------------------------------
# Parsing a recorded run
# --------------------------------------------------------------------------


def test_detects_claude_stream_but_not_altimate_events():
    assert g.is_claude_stream(stream())
    assert not g.is_claude_stream([{"type": "step_finish", "part": {"cost": 1}},
                                   {"type": "tool_use", "part": {"tool": "bash", "state": {}}}])


def test_recorded_run_tool_calls_skill_bash_and_files():
    ev = stream()
    assert g.skill_invocations(ev) == [{"name": "authoring-airflow-dags", "origin": None, "status": "completed"}]
    cmds = g.bash_commands(ev)
    assert len(cmds) == 9 and cmds[0].startswith("ls -R .")
    assert g.ran_command_matching(ev, r"airflow_check\.py")
    assert g.edited_files(ev) == ["/work/campaign/attempt/ws/dags/event_counts.py"]
    reads = [u["input"]["file_path"] for u in g.tool_uses(ev, "read")]
    assert reads == ["/work/campaign/attempt/ws/dags/orders_daily.py"]
    errored = [u for u in g.tool_uses(ev, "bash") if u["status"] == "error"]
    assert len(errored) == 3 and "Operation not permitted" in errored[1]["output"]


def test_recorded_run_usage_termination_and_classification():
    ev = stream()
    use = g.usage(ev, "claude-sonnet-5-5")
    assert use["cost_usd"] == pytest.approx(0.1874388, abs=1e-6) == use["cost_usd_equivalent"]
    assert use["cost_source"] == "result" and use["steps"] == 14
    assert use["tokens"]["cache_read"] == 272124 and use["tokens"]["output"] == 4017
    assert use["cost_list_price_usd"] is not None
    assert g.termination(ev)["why_harness_stopped"] == "completed"
    assert g.model_steps(ev) > 0 and g.error_messages(ev) == []
    ok = r.classify_attempt(timed_out=False, cost_capped=False, returncode=0, events=ev, stderr="",
                            grade={"primary_pass": True, "checks": []}, grader_failed=False)
    assert ok == ("ok", "primary checks passed")


def test_usage_estimate_without_result_dedupes_message_ids():
    u1 = {"input_tokens": 2, "output_tokens": 4, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 500,
          "cache_creation": {"ephemeral_1h_input_tokens": 500}}
    u2 = dict(u1, output_tokens=100)  # later event of the same message: larger output wins
    ev = [init([]), assistant("m1", {"type": "text", "text": "a"}, usage=u1),
          assistant("m1", {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}, usage=u2)]
    use = g.usage(ev, "claude-sonnet-5-5")
    assert use["cost_source"] == "estimate" and use["steps"] == 1
    # sonnet 5.5: 2*2 + 100*10 + 1000*0.2 + 500 * (2 * 2, 1-hour write) per MTok
    assert use["cost_usd"] == pytest.approx((4 + 1000 + 200 + 2000) / 1e6)
    assert use["tokens"]["output"] == 100


def test_subagent_and_synthetic_messages_do_not_count_as_steps():
    ev = [init([]), assistant("x", {"type": "text", "text": "Context Usage"}, model="<synthetic>"),
          assistant("s1", {"type": "text", "text": "sub"}, parent_tool_use_id="toolu_1")]
    assert g.model_steps(ev) == 0


# --------------------------------------------------------------------------
# Classification of failures
# --------------------------------------------------------------------------


def classify(ev, primary_pass=False, **kw):
    base = dict(timed_out=False, cost_capped=False, returncode=1, events=ev, stderr="",
                grade={"primary_pass": primary_pass, "checks": [{"name": "c", "kind": "primary", "passed": False}]},
                grader_failed=False)
    base.update(kw)
    return r.classify_attempt(**base)


def test_max_turns_is_turn_limit_unless_grade_passes():
    ev = [init([]), assistant("m1", {"type": "text", "text": "x"}),
          result(subtype="error_max_turns", is_error=True, text="")]
    assert g.termination(ev)["why_harness_stopped"] == "budget-exhausted"
    assert classify(ev)[0] == "turn_limit"
    assert classify(ev, primary_pass=True)[0] == "ok"


def test_timeout_without_result():
    ev = [init([]), assistant("m1", {"type": "text", "text": "x"})]
    assert classify(ev, timed_out=True)[0] == "timeout"


def test_usage_limit_is_infra_error_flagged_as_usage_limit():
    limit_msg = assistant("e1", {"type": "text", "text": "You've hit your limit · resets 5pm (UTC)"},
                          model="<synthetic>", error="rate_limit")
    ev = [init([]), limit_msg,
          {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "rateLimitType": "five_hour",
                                                            "resetsAt": 1790824800}},
          result(is_error=True, text="You've hit your limit · resets 5pm (UTC)", cost=0, turns=1)]
    status, reason = classify(ev)
    assert status == "infra_error" and "limit" in reason
    rec = {"status": status, "reason": reason, "errors": g.error_messages(ev)}
    assert cc.is_usage_limit(rec) and r.should_retry(rec)


def test_overloaded_mid_run_is_retryable_infra_error_not_usage_limit():
    ev = [init([]), assistant("m1", {"type": "text", "text": "x"}),
          {"type": "system", "subtype": "api_retry", "attempt": 10, "max_retries": 10, "retry_delay_ms": 0,
           "error_status": 529, "error": "overloaded_error"},
          result(is_error=True, text="API Error: 529 Overloaded", api_error_status=529)]
    status, reason = classify(ev)
    assert status == "infra_error"
    rec = {"status": status, "reason": reason, "errors": g.error_messages(ev)}
    assert r.should_retry(rec) and not cc.is_usage_limit(rec)


def test_auth_failure_before_any_step_is_infra_error():
    ev = [init([]), assistant("e1", {"type": "text", "text": "Invalid API key · Please run /login"},
                              model="<synthetic>", error="authentication_failed"),
          result(is_error=True, text="Invalid API key · Please run /login", cost=0, turns=1)]
    status, reason = classify(ev)
    assert status == "infra_error" and reason.startswith("no model steps completed")
    assert not cc.is_usage_limit({"status": status, "reason": reason, "errors": g.error_messages(ev)})


def test_task_fail_with_normal_result():
    ev = [init([]), assistant("m1", {"type": "text", "text": "x"}), result()]
    assert classify(ev)[0] == "task_fail"


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------


def test_inventory_from_recorded_init_matches_skill_arm():
    inv = cc.inventory_from_events(stream())
    assert cc.check_inventory("skill", inv, AIRFLOW, REPO) == []
    problems = cc.check_inventory("baseline", inv, AIRFLOW, REPO)
    assert len(problems) == 3 and all("present in baseline" in p for p in problems)


def test_inventory_problems():
    base = cc.inventory_from_events([init(REPO + ["dataviz"])])
    assert cc.check_inventory("baseline", base, AIRFLOW, REPO) == []
    assert any("missing in skill arm" in p for p in cc.check_inventory("skill", base, AIRFLOW, REPO))
    assert any("repo skill" in p for p in cc.check_inventory("baseline", base, AIRFLOW, REPO + ["x"]))
    bad = cc.inventory_from_events([init(REPO, mcp_servers=[{"name": "slack"}],
                                         plugins=[{"name": "p", "path": "/home/u/.claude/plugins/p", "source": "p@m"}],
                                         memory_paths={"auto": "/x/memory/"})])
    problems = cc.check_inventory("baseline", bad, AIRFLOW, REPO)
    assert any("MCP" in p for p in problems) and any("plugin" in p for p in problems)
    assert any("auto-memory" in p for p in problems)
    assert cc.check_inventory("baseline", None, AIRFLOW, REPO) == ["no system/init event in the stream"]


def test_context_inventory_sources_and_memory_files():
    inv = cc.inventory_from_events(stream("claude_stream_context.jsonl"), with_context=True)
    names = {s["name"]: s["source"] for s in inv["context_skills"]}
    assert names["probe-skill"] == "User" and names["dataviz"] == "Built-in"
    assert inv["context_memory_files"] == []
    # probe-skill is a User skill outside the arm spec
    assert any("unexpected User skill 'probe-skill'" in p
               for p in cc.check_inventory("baseline", inv, [], ["probe-skill-missing"]))
    text = ("## Context Usage\n\n### Memory files\n\n| Type | Path | Tokens |\n|---|---|---|\n"
            "| Project | /home/u/.claude/CLAUDE.md | 900 |\n\n### Skills\n\n| Skill | Source | Tokens |\n"
            "|---|---|---|\n| a | User | 1 |\n")
    parsed = cc.parse_context(text)
    assert parsed["memory_files"] == ["Project"] and parsed["skills"] == [{"name": "a", "source": "User"}]
    inv2 = dict(inv, context_memory_files=parsed["memory_files"], context_skills=parsed["skills"])
    assert any("memory files loaded" in p for p in cc.check_inventory("baseline", inv2, [], ["a"]))


def test_stream_monitor_aborts_on_inventory_mismatch_and_tracks_cost(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps(init(REPO + AIRFLOW)) + "\n" + '{"type":"assista')  # partial line
    mon = cc.StreamMonitor(path, "claude-sonnet-5-5", g.claude_running_cost,
                           on_init=lambda inv: cc.check_inventory("baseline", inv, AIRFLOW, REPO))
    mon.poll()
    assert mon.abort_reason and "present in baseline" in mon.abort_reason
    ok = cc.StreamMonitor(path, "claude-sonnet-5-5", g.claude_running_cost,
                          on_init=lambda inv: cc.check_inventory("skill", inv, AIRFLOW, REPO))
    ok.poll()
    assert ok.abort_reason is None and ok.cost == 0
    with path.open("a") as fh:
        fh.write('nt","message":{"id":"m1","model":"claude-sonnet-5-5","content":[],'
                 '"usage":{"input_tokens":1000000,"output_tokens":0}}}\n')
    assert ok.poll() == pytest.approx(2.0)  # 1M uncached input tokens at $2/MTok
    with path.open("a") as fh:
        fh.write(json.dumps(result(cost=1.25)) + "\n")
    assert ok.poll() == pytest.approx(1.25)


# --------------------------------------------------------------------------
# Skills, env, command
# --------------------------------------------------------------------------


def skill(root: Path, rel: str, name: str | None) -> None:
    d = root / rel
    d.mkdir(parents=True)
    fm = f"---\nname: {name}\ndescription: x: y\n---\nbody\n" if name else "no frontmatter\n"
    (d / "SKILL.md").write_text(fm)
    (d / "references").mkdir()
    (d / "references" / "a.md").write_text("ref")


def test_flatten_skills(tmp_path):
    staged = tmp_path / "staged"
    skill(staged, "dbt/creating-dbt-models", "creating-dbt-models")
    skill(staged, "altimate-code", "altimate-code")
    skill(staged, "airflow/authoring-airflow-dags", "authoring-airflow-dags")
    skill(staged, "airflow/_shared", "shared-not-a-skill")
    skill(staged, "x/dir-name", None)
    names = cc.flatten_skills(staged, tmp_path / "flat")
    assert sorted(names) == ["altimate-code", "authoring-airflow-dags", "creating-dbt-models", "dir-name"]
    assert (tmp_path / "flat" / "creating-dbt-models" / "references" / "a.md").read_text() == "ref"
    assert not (tmp_path / "flat" / "shared-not-a-skill").exists()
    skill(staged, "y/dup", "altimate-code")
    with pytest.raises(ValueError, match="duplicate"):
        cc.flatten_skills(staged, tmp_path / "flat2")


def test_agent_env_scrubs_host_claude_vars_and_keeps_token(tmp_path):
    base = {"PATH": "/usr/bin", "TMPDIR": str(tmp_path / "tmp"), "CLAUDECODE": "1", "CLAUDE_CONFIG_DIR": "/home/u/.c",
            "CLAUDE_CODE_SESSION_ID": "s", "ANTHROPIC_API_KEY": "k", "CLAUDE_CODE_OAUTH_TOKEN": "tok",
            "CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/s"}
    env = cc.agent_env(base, tmp_path / "cfg")
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "cfg") and env["CLAUDE_CODE_OAUTH_TOKEN"] == "tok"
    for k in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "ANTHROPIC_API_KEY", "CLAUDE_CODE_MESSAGING_SOCKET"):
        assert k not in env
    assert env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1" and env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert env["DISABLE_AUTOUPDATER"] == "1" and env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert env["CLAUDE_CODE_TMPDIR"] == base["TMPDIR"] and env["TMPPREFIX"].startswith(base["TMPDIR"])


def test_prepare_config_dir_and_command(tmp_path):
    flat = tmp_path / "flat"
    skill(flat, "s1", "s1")
    cfg, mcp = cc.prepare_config_dir(tmp_path / "scratch", flat)
    assert (cfg / "skills" / "s1" / "SKILL.md").exists() and json.loads(mcp.read_text()) == {"mcpServers": {}}
    cmd = cc.command("claude-opus-5-5", 40, "--do things", mcp)
    assert cmd[:2] == [cc.CLAUDE_BIN, "-p"] and cmd[-2:] == ["--", "--do things"]
    for flag in ("--strict-mcp-config", "--dangerously-skip-permissions", "--verbose", f"--mcp-config={mcp}"):
        assert flag in cmd
    assert cmd[cmd.index("--output-format") + 1] == "stream-json" and cmd[cmd.index("--max-turns") + 1] == "40"
    assert cc.inventory_command("m", mcp)[-1] == "/context"


def test_ancestor_memory_files(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "CLAUDE.md").write_text("x")
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "AGENTS.md").write_text("x")
    found = cc.ancestor_memory_files(tmp_path / "a" / "b", stop=tmp_path)
    assert found == [str(tmp_path / "a" / "AGENTS.md"), str(tmp_path / ".claude" / "CLAUDE.md")]


def test_claude_sandbox_profile_and_policy(tmp_path):
    roots = r.IsolationRoots(scratch=tmp_path / "work" / "camp" / "att", agent_venv=tmp_path / "venv",
                             staged_skills=tmp_path / "work" / "camp" / "skills", out_dir=None,
                             work_root=tmp_path / "work", base={"HOME": str(tmp_path / "home")}, runner="claude-code")
    prof = roots.sandbox_profile()
    assert "file-read-metadata" in prof and os.path.realpath(tmp_path / "work") in prof
    assert ".claude.json" in prof and "altimate-code" not in prof.split("(allow file-write*")[1].split(")")[0]
    labels = {label for label, _ in roots.forbidden()}
    assert "user-config" in labels
    alt = r.IsolationRoots(scratch=roots.scratch, agent_venv=roots.agent_venv, staged_skills=roots.staged_skills,
                           out_dir=None, work_root=roots.work_root, base=roots.base)
    # Both runners need stat-only access to runtime ancestors after denying the
    # entire eval cache; this does not grant directory listings or file contents.
    assert "file-read-metadata" in alt.sandbox_profile()
    assert f'(literal "{os.path.realpath(tmp_path / "work")}")' in alt.sandbox_profile()
    assert "user-config" not in {x for x, _ in alt.forbidden()}


def test_contamination_scan_on_claude_tool_calls(tmp_path):
    roots = r.IsolationRoots(scratch=tmp_path / "work" / "att", agent_venv=tmp_path / "venv",
                             staged_skills=tmp_path / "work" / "skills", out_dir=None, work_root=tmp_path / "work",
                             base={"HOME": str(tmp_path / "home")}, runner="claude-code")
    ev = [init([]),
          assistant("m1", {"type": "tool_use", "id": "t1", "name": "Read",
                           "input": {"file_path": str(r.REPO_ROOT / "evals/airflow/cases/x/reference/dags/a.py")}}),
          assistant("m1", {"type": "tool_use", "id": "t2", "name": "Bash",
                           "input": {"command": f"cat {tmp_path}/home/.claude.json"}}),
          assistant("m1", {"type": "tool_use", "id": "t3", "name": "Grep",
                           "input": {"pattern": "x", "path": str(tmp_path / "work" / "att" / "ws")}}),
          {"type": "user", "message": {"content": [
              {"type": "tool_result", "tool_use_id": "t2", "content": "cat: Operation not permitted",
               "is_error": True}]}}]
    rep = r.isolation_report(ev, roots)
    assert rep["contamination_suspect"] and [h["root"] for h in rep["hits"]] == ["repo"]
    assert [h["root"] for h in rep["denied_hits"]] == ["user-config"]


# --------------------------------------------------------------------------
# Usage-limit gate, retries, resume
# --------------------------------------------------------------------------


class Clock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_usage_limit_gate_backoff_caps_at_30_minutes_then_stops():
    clk = Clock()
    gate = cc.UsageLimitGate(clock=clk, sleep=clk.sleep)
    waits = []
    while gate.report_limit("hit your limit"):
        start = clk.t
        assert gate.wait()
        waits.append(clk.t - start)
    assert waits == [120, 240, 480, 960] and gate.waited_s == pytest.approx(1800)
    assert gate.stopped and not gate.wait() and gate.events[-1]["action"] == "stop"


def test_usage_limit_gate_shared_pause_and_reset():
    clk = Clock()
    gate = cc.UsageLimitGate(clock=clk, sleep=clk.sleep)
    assert gate.report_limit("a") and gate.report_limit("b")  # second worker joins the same pause
    assert gate.level == 1
    gate.wait()
    gate.report_ok()
    assert gate.level == 0 and gate.report_limit("c") and gate.paused_until - clk.t == 120


class _Budget:
    spent = 0.0

    def can_launch(self):
        return True

    def add(self, usd):
        self.spent += usd


def _ctx(gate=None, runner="claude-code"):
    return r.AttemptContext(out_dir=None, work_dir=Path("."), staged_skills=Path("."), runner=runner,
                            usage_gate=gate)


def test_attempt_loop_waits_out_usage_limit_then_succeeds():
    clk = Clock()
    gate = cc.UsageLimitGate(clock=clk, sleep=clk.sleep)
    outcomes = iter([{"status": "infra_error", "reason": "usage limit reached: rejected", "cost_usd": 0},
                     {"status": "ok", "reason": "primary checks passed", "cost_usd": 1.0}])
    row = {"attempts": []}
    r.attempt_loop(row, lambda k: dict(next(outcomes)), _ctx(gate), _Budget(), "c m run-1", sleep=clk.sleep)
    assert [a["status"] for a in row["attempts"]] == ["infra_error", "ok"]
    assert row["attempts"][0]["usage_limit"] and [a["attempt"] for a in row["attempts"]] == [0, 1]
    assert clk.slept == [30, 30, 30, 30] and gate.level == 0


def test_attempt_loop_stops_cleanly_when_usage_limit_persists():
    clk = Clock()
    gate = cc.UsageLimitGate(clock=clk, sleep=clk.sleep)
    row = {"attempts": []}
    r.attempt_loop(row, lambda k: {"status": "infra_error", "reason": "You've hit your limit", "cost_usd": 0},
                   _ctx(gate), _Budget(), "c m run-1", sleep=clk.sleep)
    assert row["attempts"][-1]["status"] == "skipped_usage_limit" and gate.stopped
    assert sum(1 for a in row["attempts"] if a.get("usage_limit")) == 5
    nxt = {"attempts": []}
    r.attempt_loop(nxt, lambda k: pytest.fail("must not launch"), _ctx(gate), _Budget(), "c2", sleep=clk.sleep)
    assert [a["status"] for a in nxt["attempts"]] == ["skipped_usage_limit"]
    assert r.finalize_row({**nxt})["status"] == "skipped_usage_limit"


def test_attempt_loop_claude_infra_retries_with_exponential_backoff():
    slept = []
    row = {"attempts": []}
    r.attempt_loop(row, lambda k: {"status": "infra_error", "reason": "API Error: 529 overloaded", "cost_usd": 0},
                   _ctx(cc.UsageLimitGate()), _Budget(), "c m run-1", first=2, sleep=slept.append)
    assert len(row["attempts"]) == 4 and slept == [30, 60, 120]
    assert [a["attempt"] for a in row["attempts"]] == [2, 3, 4, 5]
    alt = {"attempts": []}
    slept.clear()
    r.attempt_loop(alt, lambda k: {"status": "infra_error", "reason": "429 rate limit", "cost_usd": 0},
                   _ctx(runner="altimate-code"), _Budget(), "c", sleep=slept.append)
    assert len(alt["attempts"]) == 3 and slept == [20, 40]


def test_attempt_loop_skips_after_abort():
    ctx = _ctx(cc.UsageLimitGate())
    ctx.abort_reason = "inventory mismatch: x"
    row = {"attempts": []}
    r.attempt_loop(row, lambda k: pytest.fail("must not launch"), ctx, _Budget(), "c")
    assert row["attempts"][0]["status"] == "skipped_abort"


def test_next_attempt_index(tmp_path):
    assert r.next_attempt_index(tmp_path / "missing") == 0
    for k in (0, 1, 3):
        (tmp_path / f"attempt-{k}").mkdir()
    assert r.next_attempt_index(tmp_path) == 4


def test_load_resume_splits_done_and_redo(tmp_path):
    p = tmp_path / "runs.jsonl"
    rows = [{"case": "a", "model": "m", "run": 1, "status": "infra_error", "cost_usd": 0.1},
            {"case": "a", "model": "m", "run": 1, "status": "ok", "cost_usd": 1.0},  # later row wins
            {"case": "b", "model": "m", "run": 1, "status": "task_fail"},
            {"case": "c", "model": "m", "run": 1, "status": "skipped_usage_limit"},
            {"case": "d", "model": "m", "run": 2, "status": "harness_error"}]
    p.write_text("\n".join(json.dumps(x) for x in rows) + "\n\n")
    done, redo = r.load_resume(p)
    assert set(done) == {("a", "m", 1), ("b", "m", 1)} and done[("a", "m", 1)]["status"] == "ok"
    assert set(redo) == {("c", "m", 1), ("d", "m", 2)}
    assert r.load_resume(tmp_path / "none.jsonl") == ({}, {})


def test_resume_meta_problems():
    args = r.argparse.Namespace(arm="skill", runner="claude-code")
    assert r.resume_meta_problems({"arm": "skill", "runner": "claude-code", "models": ["m"]}, args, ["m"]) == []
    probs = r.resume_meta_problems({"arm": "baseline", "models": ["m"]}, args, ["m", "n"])
    assert len(probs) == 3
    meta = {"arm": "skill", "runner": "claude-code", "models": ["m"], "airflow_skills_sha256": "aa",
            "cases": {"c1": {"sha256": "x"}, "c2": {"sha256": "y"}}}
    assert r.resume_meta_problems(meta, args, ["m"], {"c1": "x", "c2": "y", "c3": "z"}, "aa") == []
    probs = r.resume_meta_problems(meta, args, ["m"], {"c1": "CHANGED"}, "bb")
    assert len(probs) == 2 and "c1" in probs[0] and "skills/airflow" in probs[1]


def test_parse_args_runner_defaults():
    a = r.parse_args(["--arm", "skill", "--out", "/x/y", "--runner", "claude-code"])
    assert a.models.split(",") == list(cc.DEFAULT_MODELS) and not a.resume
    b = r.parse_args(["--arm", "skill", "--out", "/x/y"])
    assert b.runner == "altimate-code" and b.models.split(",") == list(r.DEFAULT_MODELS)


# --------------------------------------------------------------------------
# run_attempt end to end with a recorded stream (no claude process)
# --------------------------------------------------------------------------


def test_run_attempt_claude_code_records(tmp_path, monkeypatch):
    from test_run_eval import make_case

    case = r.load_case(make_case(tmp_path / "cases", "c1"))
    recorded = (FIXTURES / "claude_stream_skill_run.jsonl").read_text()
    seen = {}

    def fake_process(cmd, cwd, env, events_path, stderr_path, timeout_s, cap, model, correct, spool_dir=None,
                     monitor_factory=None):
        seen.update(cmd=cmd, env=env)
        events_path.write_text(recorded + json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "x", "content": "token sk-ant-oat01-AbCdEf123456_-xyz"}]}}) + "\n")
        r.san.redact_file(events_path)
        stderr_path.write_text("")
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
    budget = _Budget()
    rec = r.run_attempt(case, "claude-sonnet-5-5", "skill", tmp_path / "out" / "attempt-0", tmp_path / "staged",
                        set(AIRFLOW), args, budget)
    assert rec["status"] == "ok" and rec["runner"] == "claude-code" and rec["inventory_problems"] == []
    assert rec["cost_usd_equivalent"] == pytest.approx(0.1874388, abs=1e-6) == budget.spent
    assert rec["airflow_skills_used"] == ["authoring-airflow-dags"] and rec["num_turns"] == 14
    assert seen["cmd"][0] == cc.CLAUDE_BIN and "CLAUDECODE" not in seen["env"]
    assert seen["env"]["CLAUDE_CONFIG_DIR"].endswith(cc.CONFIG_DIR_NAME)
    out = tmp_path / "out" / "attempt-0"
    assert (out / "final.md").exists()
    for f in out.iterdir():
        assert "sk-ant-" not in f.read_text(errors="replace"), f

    # the same stream in the baseline arm is a setup error: abort, no grading, campaign stops
    args.ctx.arm = "baseline"
    rec2 = r.run_attempt(case, "claude-sonnet-5-5", "baseline", tmp_path / "out2" / "attempt-0",
                         tmp_path / "staged", set(AIRFLOW), args, budget)
    assert rec2["status"] == "harness_error" and rec2["aborted"] and "inventory mismatch" in rec2["reason"]
    assert args.ctx.abort_reason


def test_transient_429_is_not_a_usage_limit():
    rec = {"status": "infra_error", "reason": "rate_limit: API Error: Rate limit reached for requests",
           "errors": ["api_retry 10/10 (HTTP 429): rate_limit"]}
    assert not cc.is_usage_limit(rec) and r.should_retry(rec)


def test_attempt_inventory_rejects_skills_beyond_campaign_inventory():
    ctx = r.AttemptContext(out_dir=None, work_dir=Path("."), staged_skills=Path("."), runner="claude-code",
                           arm="baseline", airflow_names=AIRFLOW, repo_names=REPO, expected_skills=REPO + ["dataviz"])
    assert ctx.check_inventory(cc.inventory_from_events([init(REPO + ["dataviz"])])) == []
    probs = ctx.check_inventory(cc.inventory_from_events([init(REPO + ["dataviz", "project-skill"])]))
    assert probs == ["skills not in the campaign inventory: ['project-skill']"]


def test_attempt_loop_rechecks_abort_and_budget_after_pause():
    clk = Clock()
    gate = cc.UsageLimitGate(clock=clk, sleep=clk.sleep)
    ctx = _ctx(gate)
    gate.report_limit("limit")

    def sleep_then_abort(s):
        clk.sleep(s)
        ctx.abort_reason = "inventory mismatch"

    gate._sleep = sleep_then_abort
    row = {"attempts": []}
    r.attempt_loop(row, lambda k: pytest.fail("must not launch"), ctx, _Budget(), "c")
    assert [a["status"] for a in row["attempts"]] == ["skipped_abort"]


def test_compact_rows_keeps_last_row_per_run(tmp_path):
    p = tmp_path / "runs.jsonl"
    rows = [{"case": "a", "model": "m", "run": 1, "status": "infra_error"},
            {"case": "b", "model": "m", "run": 1, "status": "ok"},
            {"case": "a", "model": "m", "run": 1, "status": "ok", "attempts": [{"status": "infra_error"}, {}]}]
    p.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    r.compact_rows(p)
    kept = [json.loads(x) for x in p.read_text().splitlines()]
    assert [(x["case"], x["status"]) for x in kept] == [("b", "ok"), ("a", "ok")]


def test_trigger_metrics_skip_unlaunched_rows():
    import run_triggers as t

    rows = [{"expected": "authoring-airflow-dags", "fired": [], "status": s}
            for s in ("skipped_usage_limit", "skipped_abort")]
    m = t.compute_metrics(rows, AIRFLOW)
    assert m["scored_runs"] == 0 and m["unscored_runs"] == {"skipped_usage_limit": 1, "skipped_abort": 1}
