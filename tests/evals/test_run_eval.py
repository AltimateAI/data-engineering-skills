"""Unit tests for the pure parts of evals/harness/run_eval.py (no LLM, no Airflow)."""

import json
from pathlib import Path

import pytest
import run_eval as r

CASE_YAML = """id: {id}
area: authoring
split: {split}
airflow_version: "3.3"
prompt: |
  Do the thing.
"""


def make_case(root: Path, cid: str, split: str = "dev", mutants=("m1",), alt=False) -> Path:
    d = root / cid
    for sub in ("fixture/dags", "reference/dags"):
        (d / sub).mkdir(parents=True)
    (d / "case.yaml").write_text(CASE_YAML.format(id=cid, split=split))
    (d / "grade.py").write_text("")
    (d / "fixture" / "dags" / "a.py").write_text("x = 1\n")
    for m in mutants:
        (d / "mutants" / m).mkdir(parents=True)
    if alt:
        (d / "alt_reference").mkdir()
    return d


def test_load_case_defaults(tmp_path):
    c = r.load_case(make_case(tmp_path, "c1"))
    assert (c.id, c.area, c.split, c.airflow_version) == ("c1", "authoring", "dev", "3.3")
    assert c.prompt == "Do the thing." and c.max_turns == 40 and c.timeout_s == 900
    assert c.env_py.endswith("airflow-3.3/bin/python")


def test_load_case_validation(tmp_path):
    d = make_case(tmp_path, "c1")
    (d / "case.yaml").write_text("id: other\narea: cooking\nsplit: train\nairflow_version: 2.10\n")
    with pytest.raises(ValueError) as exc:
        r.load_case(d)
    msg = str(exc.value)
    for fragment in ("missing prompt", "directory name", "area must be", "split must be", "airflow_version"):
        assert fragment in msg
    # unquoted 2.10 parses as the float 2.1, hence the "quote it" hint


def test_discover_cases_filters(tmp_path):
    make_case(tmp_path, "a", "dev")
    make_case(tmp_path, "b", "holdout")
    make_case(tmp_path, "_example", "dev")
    assert [c.id for c in r.discover_cases(tmp_path)] == ["a", "b"]
    assert [c.id for c in r.discover_cases(tmp_path, "holdout")] == ["b"]
    assert [c.id for c in r.discover_cases(tmp_path, "all", ["_example"])] == ["_example"]
    with pytest.raises(SystemExit):
        r.discover_cases(tmp_path, "all", ["nope"])


def test_selftest_variants(tmp_path):
    c = r.load_case(make_case(tmp_path, "c1", mutants=("m1", "m2"), alt=True))
    labels = [(v[0], len(v[1]), v[2]) for v in r.selftest_variants(c)]
    assert labels == [("reference", 1, True), ("alt_reference", 1, True), ("fixture", 0, False),
                      ("mutant:m1", 2, False), ("mutant:m2", 2, False)]


def test_hash_dir_ignores_caches_and_detects_changes(tmp_path):
    d = make_case(tmp_path, "c1")
    h1 = r.hash_dir(d)
    (d / "fixture" / "dags" / "__pycache__").mkdir()
    (d / "fixture" / "dags" / "__pycache__" / "a.pyc").write_bytes(b"x")
    (d / ".DS_Store").write_text("x")
    assert r.hash_dir(d) == h1
    (d / "fixture" / "dags" / "a.py").write_text("x = 2\n")
    assert r.hash_dir(d) != h1
    assert r.hash_dir(tmp_path / "missing") == "missing"


def test_frontmatter_and_skill_names(tmp_path):
    (tmp_path / "s1").mkdir()
    (tmp_path / "s1" / "SKILL.md").write_text("---\nname: one\ndescription: d\n---\nbody")
    (tmp_path / "s2").mkdir()
    (tmp_path / "s2" / "SKILL.md").write_text("no frontmatter")
    assert r.skill_names(tmp_path) == ["one"]
    assert r.parse_frontmatter("---\n: [bad\n---\n") == {}


def test_stage_skills_arms(tmp_path):
    repo = tmp_path / "skills"
    for sub in ("dbt/x", "airflow/y"):
        (repo / sub).mkdir(parents=True)
        (repo / sub / "SKILL.md").write_text(f"---\nname: {sub.split('/')[1]}\n---\n")
    base = r.stage_skills("baseline", repo, repo / "airflow", tmp_path / "stage-b")
    assert (base / "dbt" / "x").exists() and not (base / "airflow").exists()
    skill = r.stage_skills("skill", repo, repo / "airflow", tmp_path / "stage-s")
    assert (skill / "airflow" / "y" / "SKILL.md").exists()
    with pytest.raises(SystemExit):
        r.stage_skills("skill", repo, tmp_path / "nope", tmp_path / "stage-x")


def test_check_inventory(tmp_path):
    staged = tmp_path / "staged"
    inv = [{"name": "dbt-x", "location": str(staged / "dbt/x/SKILL.md")},
           {"name": "af-y", "location": str(staged / "airflow/y/SKILL.md")}]
    assert r.check_inventory("skill", inv, staged, ["af-y"], ["dbt-x"]) == []
    problems = r.check_inventory("baseline", inv, staged, ["af-y"], ["dbt-x"])
    assert any("present in baseline" in p for p in problems)
    assert any("missing" in p for p in r.check_inventory("skill", inv[:1], staged, ["af-y"], ["dbt-x"]))
    leak = [{"name": "dbt-x", "location": str(r.REPO_ROOT / "skills/dbt/x/SKILL.md")}]
    assert any("repo checkout" in p for p in r.check_inventory("baseline", leak, staged, [], ["dbt-x"]))


STEP = {"type": "step_finish", "part": {"cost": 0.1, "tokens": {}}}


def classify(**kw):
    base = dict(timed_out=False, cost_capped=False, returncode=0, events=[STEP], stderr="",
                grade={"primary_pass": True, "checks": []}, grader_failed=False)
    base.update(kw)
    return r.classify_attempt(**base)[0]


def test_classify_attempt():
    fail = {"primary_pass": False, "checks": [{"name": "runs", "kind": "primary", "passed": False}]}
    assert classify() == "ok"
    assert classify(grade=fail) == "task_fail"
    assert classify(events=[], stderr="boom") == "infra_error"
    err = {"type": "error", "error": {"name": "APIError", "data": {"message": "429 Too Many Requests: rate limit"}}}
    term = {"type": "termination", "why_harness_stopped": "error"}
    assert classify(events=[STEP, err, term], grade=fail) == "infra_error"
    assert classify(events=[STEP, err], grade=fail) == "task_fail"  # error recovered, run continued
    assert classify(timed_out=True, grade=fail) == "timeout"
    assert classify(timed_out=True) == "ok"
    assert classify(cost_capped=True, grade=fail) == "cost_limit"
    budget = {"type": "termination", "why_harness_stopped": "budget-exhausted"}
    assert classify(events=[STEP, budget], grade=fail) == "turn_limit"
    assert classify(grade=None, grader_failed=True) == "grader_error"


def test_stream_cost_reads_only_complete_lines(tmp_path):
    p = tmp_path / "e.jsonl"
    p.write_text(json.dumps(STEP) + "\n" + '{"type": "text"}\n' + '{"type": "step_fin')
    cost, off = r._stream_cost(p, 0)
    assert cost == pytest.approx(0.1)
    with p.open("a") as fh:
        fh.write('ish", "part": {"cost": 0.2}}\n')
    cost2, off2 = r._stream_cost(p, off)
    assert cost2 == pytest.approx(0.2) and off2 > off
    assert r._stream_cost(tmp_path / "missing", 0) == (0.0, 0)


def test_auto_loaded_skills(tmp_path):
    t = tmp_path / "trace.json"
    t.write_text(json.dumps({"spans": [{"input": '<auto_loaded_skill name="af-y">body</auto_loaded_skill>'}]}))
    assert r.auto_loaded_skills(str(t)) == ["af-y"]
    assert r.auto_loaded_skills(None) == []


def test_build_agent_env_isolation(tmp_path):
    host = {"PATH": "/usr/bin", "HOME": "/home/me", "AIRFLOW__CORE__X": "1", "AIRFLOW_HOME": "/af",
            "OPENCODE_CONFIG_CONTENT": "{}", "ALTIMATE_ROUTER_ENABLE_MODEL_SWAP": "1",
            "GOOGLE_CLOUD_PROJECT": "p", "VIRTUAL_ENV": "/other"}
    env = r.build_agent_env(tmp_path / "att", tmp_path / "ws", tmp_path / "skills",
                            "/venvs/airflow-3.3/bin/python", base=host)
    assert "ALTIMATE_ROUTER_ENABLE_MODEL_SWAP" not in env and "AIRFLOW__CORE__X" not in env
    assert env["GOOGLE_CLOUD_PROJECT"] == "p" and env["HOME"] == "/home/me"
    assert env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "1"
    assert env["OPENCODE_TEST_HOME"] != env["XDG_CONFIG_HOME"]
    cfg = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    assert cfg["skills"]["paths"] == [str(tmp_path / "skills")]
    assert env["VIRTUAL_ENV"] == "/venvs/airflow-3.3" and env["PATH"].startswith("/venvs/airflow-3.3/bin")
    assert env["AIRFLOW__CORE__DAGS_FOLDER"] == str(tmp_path / "ws" / "dags")
    assert Path(env["OPENCODE_TEST_HOME"]).is_dir() and not any(Path(env["OPENCODE_TEST_HOME"]).iterdir())


def test_find_enclosing_git(tmp_path):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    (tmp_path / "repo" / "a" / "b").mkdir(parents=True)
    assert r.find_enclosing_git(tmp_path / "repo" / "a" / "b") == tmp_path / "repo"


def test_budget():
    b = r.Budget(1.0)
    assert b.can_launch()
    b.add(0.6)
    b.add(0.6)
    assert not b.can_launch() and b.stopped


def test_slug():
    assert r.slug("google-vertex-anthropic/claude-haiku-4-5@20251001") == \
        "google-vertex-anthropic_claude-haiku-4-5_20251001"


def test_run_jobs_offset_indices(tmp_path):
    cases = [r.load_case(make_case(tmp_path, cid)) for cid in ("c1", "c2")]
    jobs = r.run_jobs(cases, ["m1", "m2"], runs=2)
    assert sorted({i for (_, _, i) in jobs}) == [1, 2] and len(jobs) == 8
    only3 = r.run_jobs(cases, ["m1", "m2"], runs=1, run_offset=2)
    assert {i for (_, _, i) in only3} == {3} and len(only3) == 4
    assert {(c.id, m) for (c, m, _) in only3} == {(c, m) for c in ("c1", "c2") for m in ("m1", "m2")}


def test_parse_args_run_offset(tmp_path):
    a = r.parse_args(["--arm", "baseline", "--out", str(tmp_path), "--runs", "1", "--run-offset", "2"])
    assert (a.runs, a.run_offset) == (1, 2)
    assert r.parse_args(["--arm", "baseline", "--out", str(tmp_path)]).run_offset == 0
    with pytest.raises(SystemExit):
        r.parse_args(["--arm", "baseline", "--out", str(tmp_path), "--run-offset", "-1"])


def test_stop_process_group_tolerates_exited_group(monkeypatch):
    class Proc:
        pid = 12345

        def wait(self, timeout=None):
            raise AssertionError("not reached")

    calls = []

    def killpg(pid, sig):
        calls.append(sig)
        raise PermissionError(1, "Operation not permitted")  # macOS: group already exited

    monkeypatch.setattr(r.os, "killpg", killpg)
    r.stop_process_group(Proc())
    assert calls == [r.signal.SIGTERM]


def test_stop_process_group_escalates_to_sigkill(monkeypatch):
    class Proc:
        pid = 12345

        def wait(self, timeout=None):
            raise r.subprocess.TimeoutExpired("x", timeout)

    calls = []
    monkeypatch.setattr(r.os, "killpg", lambda pid, sig: calls.append(sig))
    r.stop_process_group(Proc(), grace_s=0)
    assert calls == [r.signal.SIGTERM, r.signal.SIGKILL]


def test_run_caps_scale_per_model():
    sonnet = "google-vertex-anthropic/claude-sonnet-5-5@default"
    fable = "google-vertex-anthropic/claude-fable-5-1@default"
    assert r.run_cap_for(sonnet, {}, None) == r.DEFAULT_RUN_CAP_USD["claude-sonnet-5-5"]
    assert r.run_cap_for(fable, {}, None) > r.run_cap_for(sonnet, {}, None)
    assert r.run_cap_for("x/unknown", {}, None) == r.FALLBACK_RUN_CAP_USD
    assert r.run_cap_for(sonnet, {}, 3.0) == 3.0
    assert r.run_cap_for(fable, {"claude-fable-5-1": 40}, 3.0) == 40
    assert r.run_cap_for(fable, {fable: 41}, None) == 41
    assert r.parse_cap_map("claude-opus-5-5=10, a/b@c=2.5") == {"claude-opus-5-5": 10.0, "a/b@c": 2.5}
    with pytest.raises(ValueError):
        r.parse_cap_map("nope")
    a = r.parse_args(["--arm", "skill", "--out", "/tmp/x", "--max-run-cost-usd-by-model", "claude-opus-5-5=12"])
    assert a.run_cap_overrides == {"claude-opus-5-5": 12.0} and a.max_run_cost_usd is None


def test_finalize_row_keeps_every_attempt_cost():
    row = {"attempts": [{"status": "infra_error", "cost_usd": 0.6, "cost_reported_usd": 2.0},
                        {"status": "infra_error", "cost_usd": 0.65,
                         "agent_env_post": {"changed": True, "restored": True}},
                        {"status": "skipped_budget", "cost_usd": 0.0, "launched": False}]}
    r.finalize_row(row)
    assert row["status"] == "skipped_budget" and row["cost_usd"] == 1.25 and row["retries"] == 1
    assert row["agent_env_restored"] and not row["agent_env_restore_failed"]
    empty = r.finalize_row({"attempts": []})
    assert empty["status"] == "harness_error" and empty["cost_usd"] == 0


class _Budget:
    def __init__(self):
        self.spent = 0.0

    def add(self, usd):
        self.spent += usd

    def can_launch(self):
        return True


def _fake_agent_setup(tmp_path, monkeypatch):
    """Patch the agent launch so run_attempt 'runs' one model step without altimate-code."""
    step = {"type": "step_finish", "part": {"cost": 0.42, "tokens": {"input": 10, "output": 5}}}

    def fake_process(cmd, cwd, env, events_path, stderr_path, timeout_s, cap, model, correct, spool_dir=None):
        events_path.write_text(json.dumps(step) + "\n")
        stderr_path.write_text("")
        return {"returncode": 0, "timed_out": False, "cost_capped": False, "wall_s": 1.0}

    monkeypatch.setattr(r, "run_agent_process", fake_process)
    monkeypatch.setattr(r.g, "agent_env_python", lambda v: str(tmp_path / "agent-env" / "bin" / "python"))
    args = r.argparse.Namespace(work_dir=tmp_path / "work", keep_workspaces=False, keep_traces=False,
                                max_run_cost_usd=None)
    args.work_dir.mkdir()
    return args


def test_run_attempt_preserves_cost_on_post_execution_exception(tmp_path, monkeypatch):
    case = r.load_case(make_case(tmp_path / "cases", "c1"))
    args = _fake_agent_setup(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("grader exploded")

    monkeypatch.setattr(r, "run_grader", boom)
    budget = _Budget()
    rec = r.run_attempt(case, "m/x", "baseline", tmp_path / "out" / "attempt-0", tmp_path / "skills", set(), args,
                        budget)
    assert rec["status"] == "harness_error" and "grader exploded" in rec["reason"]
    assert rec["cost_usd"] == pytest.approx(0.42) and budget.spent == pytest.approx(0.42)
    saved = json.loads((tmp_path / "out" / "attempt-0" / "attempt.json").read_text())
    assert saved["cost_usd"] == pytest.approx(0.42) and saved["launched"] is True
    assert saved["tmpdir"].endswith("/tmp") and "harness_exception" in saved
    assert not list((tmp_path / "work").iterdir())  # scratch cleaned up


def test_run_one_records_harness_error_without_retry(tmp_path, monkeypatch):
    case = r.load_case(make_case(tmp_path / "cases", "c1"))
    args = _fake_agent_setup(tmp_path, monkeypatch)

    def disk_error(*a, **k):
        raise OSError("disk")

    monkeypatch.setattr(r, "run_grader", disk_error)
    row = r.run_one(case, "m/x", 1, "baseline", tmp_path / "out", tmp_path / "skills", set(), args, _Budget())
    assert row["status"] == "harness_error" and len(row["attempts"]) == 1
    assert row["cost_usd"] == pytest.approx(0.42)


def test_attempt_cap_zero_means_unlimited():
    ctx = r.AttemptContext(out_dir=None, work_dir=Path("."), staged_skills=Path("."), run_caps={"m/a": 0.0, "m/b": 4})
    assert r.attempt_cap(ctx, "m/a", 9.0) == 0.0
    assert r.attempt_cap(ctx, "m/b", 9.0) == 4
    assert r.attempt_cap(ctx, "m/c", 9.0) == 9.0 and r.attempt_cap(None, "m/c", None) is None


def test_recover_usage_from_spool(tmp_path):
    spool = tmp_path / "events.jsonl"
    spool.write_text(json.dumps({"type": "step_finish", "part": {"cost": 0.3, "tokens": {}}}) + "\n")
    rec = {"cost_usd": 0.0, "launched": True}
    r.recover_usage(rec, [tmp_path / "missing.jsonl", spool], "m/x", False)
    assert rec["cost_usd"] == pytest.approx(0.3) and rec["usage_recovered_from"] == "events.jsonl"
    unlaunched = {"cost_usd": 0.0, "launched": False}
    r.recover_usage(unlaunched, [spool], "m/x", False)
    assert unlaunched["cost_usd"] == 0.0


def test_workspace_patch_ignores_agent_git_config(tmp_path):
    case = r.load_case(make_case(tmp_path / "cases", "c1"))
    ws = r.make_workspace(case, [], tmp_path / "att")
    marker = tmp_path / "pwned"
    # An agent-controlled fsmonitor hook and clean filter must not run in the harness.
    r.git(ws, "config", "core.fsmonitor", f"touch {marker}; false")
    r.git(ws, "config", "filter.evil.clean", f"touch {marker}; cat")
    (ws / ".gitattributes").write_text("*.py filter=evil\n")
    (ws / "dags" / "a.py").write_text("x = 2\n")
    (ws / "dags" / "new.py").write_text("y = 1\n")
    (ws / "dags" / "__pycache__").mkdir()
    (ws / "dags" / "__pycache__" / "a.pyc").write_bytes(b"\0")
    (ws / "airflow.cfg").write_text("fernet_key = secret\n")
    patch = r.workspace_patch(ws, case.fixture, tmp_path / "att")
    assert not marker.exists() and "airflow.cfg" not in patch
    assert "+x = 2" in patch and "dags/new.py" in patch and "__pycache__" not in patch


def test_escaping_symlinks(tmp_path):
    ws = tmp_path / "ws"
    (ws / "dags").mkdir(parents=True)
    (tmp_path / "reference.py").write_text("answer")
    (ws / "dags" / "x.py").symlink_to(tmp_path / "reference.py")
    (ws / "dags" / "real.py").write_text("x = 1\n")
    (ws / "dags" / "ok.py").symlink_to("real.py")
    found = r.escaping_symlinks(ws)
    assert len(found) == 1 and found[0].startswith("dags/x.py ->")


def test_should_retry():
    assert r.should_retry({"status": "infra_error", "reason": "429 rate limit"})
    assert not r.should_retry({"status": "task_fail", "reason": "x"})
    assert not r.should_retry({"status": "infra_error", "reason": "no model steps completed: APIError: Not Found",
                               "errors": ["Publisher model `projects/p/models/claude-x@default` was not found"]})
    assert not r.should_retry({"status": "infra_error", "reason": "Forbidden: PERMISSION_DENIED"})


def test_missing_interpreters(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_ENV_ROOT", str(tmp_path))
    msgs = r.missing_interpreters({"3.3"})
    assert len(msgs) == 2 and any("agent env" in m for m in msgs)
    (tmp_path / "airflow-3.3" / "bin").mkdir(parents=True)
    (tmp_path / "airflow-3.3" / "bin" / "python").write_text("")
    assert r.missing_interpreters({"3.3"}, agent=False) == []
