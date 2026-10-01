"""Unit tests for the pure helpers in evals/harness/grading.py (no Airflow needed)."""

import json

import grading as g
import pytest


def _tool(tool, state, **extra):
    return {"type": "tool_use", "part": {"tool": tool, "state": state, **extra}}


EVENTS = [
    {"type": "step_start", "part": {}},
    _tool("skill", {"status": "completed", "input": {"name": "authoring-airflow-dags"},
                    "metadata": {"skillOrigin": "project", "source": "builtin"}}),
    _tool("bash", {"status": "completed", "input": {"command": "airflow dags test event_counts 2026-03-01"}}),
    _tool("bash", {"status": "completed", "input": {"command": "ruff check --select AIR dags/"}}),
    _tool("write", {"status": "completed", "input": {"filePath": "/ws/dags/a.py"}}),
    _tool("edit", {"status": "completed", "input": {"filePath": "/ws/dags/a.py"}}),
    {"type": "step_finish", "part": {"cost": 0.5, "tokens": {"total": 100, "input": 80, "output": 20,
                                                             "reasoning": 0, "cache": {"read": 10, "write": 5}}}},
    {"type": "step_finish", "part": {"cost": 0.25, "tokens": {"total": 50, "input": 40, "output": 10}}},
    {"type": "error", "error": {"name": "APIError", "data": {"message": "429 rate limit"}}},
    {"type": "termination", "why_model_stopped": "stop", "why_harness_stopped": "none", "done_reason": "none"},
]


def test_event_helpers():
    assert g.skill_invocations(EVENTS) == [
        {"name": "authoring-airflow-dags", "origin": "project", "status": "completed"}]
    assert g.bash_commands(EVENTS)[0].startswith("airflow dags test")
    assert g.ran_command_matching(EVENTS, r"airflow\s+dags\s+test")
    assert not g.ran_command_matching(EVENTS, r"\bpytest\b")
    assert g.edited_files(EVENTS) == ["/ws/dags/a.py"]
    u = g.usage(EVENTS)
    assert u["cost_reported_usd"] == 0.75 and u["steps"] == 2
    assert u["cost_usd"] == pytest.approx(0.5 * (65 + 100 + 1 + 6.25) / (80 + 100 + 1 + 6.25) + 0.25, abs=1e-6)
    assert u["tokens"]["input"] == 120 and u["tokens"]["cache_read"] == 10 and u["tokens"]["total"] == 150
    assert g.termination(EVENTS)["why_harness_stopped"] == "none"
    assert g.error_messages(EVENTS) == ["APIError: 429 rate limit"]


def test_load_events_tolerates_noise(tmp_path):
    p = tmp_path / "e.jsonl"
    p.write_text('noise line\n{"type": "text"}\n{broken json\n\n{"type": "step_finish", "part": {}}\n')
    assert [e["type"] for e in g.load_events(p)] == ["text", "step_finish"]
    assert g.load_events(tmp_path / "missing.jsonl") == []
    assert g.load_events(None) == []


def test_build_result_scores():
    checks = [g.Check("a", "primary", True), g.Check("b", "primary", False), g.Check("c", "secondary", True)]
    r = g.build_result(checks)
    assert r["primary_pass"] is False and r["primary_score"] == 0.5 and r["secondary_score"] == 1.0
    assert g.build_result([g.Check("a", "primary", True)])["secondary_score"] is None
    assert g.build_result([g.Check("s", "secondary", True)])["primary_pass"] is False


def test_grader_run_and_write(tmp_path):
    gr = g.Grader()
    assert gr.run("truthy", lambda: 1)
    assert not gr.run("tuple", lambda: (False, "why"))
    assert not gr.run("raises", lambda: 1 / 0)
    gr.secondary("style", True)
    with pytest.raises(ValueError):
        gr.add("bad", True, kind="tertiary")
    res = gr.write(tmp_path / "out" / "r.json")
    saved = json.loads((tmp_path / "out" / "r.json").read_text())
    assert saved == res
    names = {c["name"]: c for c in saved["checks"]}
    assert names["tuple"]["detail"] == "why"
    assert "ZeroDivisionError" in names["raises"]["detail"]
    assert saved["primary_score"] == pytest.approx(1 / 3)


def test_grader_truncates_detail():
    gr = g.Grader()
    gr.primary("big", True, "x" * 10000)
    assert len(gr.checks[0].detail) < 5000


JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">
<testcase classname="tests.test_a" name="test_ok"/>
<testcase classname="tests.test_a" name="test_assert"><failure message="assert 1 == 2">def test_assert():
&gt;       assert x == 2
E       assert 1 == 2</failure></testcase>
<testcase classname="tests.test_a" name="test_keyerror"><failure message="KeyError: 'a'">E   KeyError: 'a'</failure></testcase>
<testcase classname="tests.test_a" name="test_inner_import"><failure message="ModuleNotFoundError: No module named 'x'">E   ModuleNotFoundError</failure></testcase>
<testcase classname="tests.test_a" name="test_setup"><error message="failed on setup with &quot;RuntimeError: boom&quot;">E   RuntimeError: boom</error></testcase>
<testcase classname="tests.test_a" name="test_skip"><skipped message="x"/></testcase>
</testsuite></testsuites>"""

JUNIT_COLLECT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">
<testcase classname="" name="tests.test_b"><error message="collection failure">E   ModuleNotFoundError: No module named 'nope'</error></testcase>
</testsuite></testsuites>"""


def test_classify_pytest_failures():
    r = g.classify_pytest(1, JUNIT)
    assert r.status == "failed"
    assert (r.passed, r.failed, r.errors, r.skipped) == (1, 3, 1, 1)
    kinds = {t.nodeid.split("::")[1]: t.exc_type for t in r.tests}
    assert kinds["test_assert"] == "AssertionError"
    assert kinds["test_keyerror"] == "KeyError"
    assert kinds["test_setup"] == "RuntimeError"
    behavioral = {t.nodeid.split("::")[1] for t in r.behavioral_failures}
    assert behavioral == {"test_assert", "test_keyerror", "test_setup"}
    assert [t.nodeid for t in r.import_failures] == ["tests.test_a::test_inner_import"]
    assert r.caught_bug
    assert "behavioral failures" in r.summary()


def test_classify_pytest_collection_error_is_not_a_caught_bug():
    r = g.classify_pytest(2, JUNIT_COLLECT, "ERROR collecting tests/test_b.py")
    assert r.status == "collection_error"
    assert r.collection_errors == ["tests.test_b"]
    assert not r.caught_bug


def test_classify_pytest_other_statuses():
    assert g.classify_pytest(0, "").status == "passed"
    assert g.classify_pytest(5, "").status == "no_tests"
    assert g.classify_pytest(4, "").status == "error"
    assert g.classify_pytest(-9, "", timed_out=True).status == "timeout"
    fallback = g.classify_pytest(2, "", "ERROR collecting tests/test_x.py\nInterrupted: 1 error during collection")
    assert fallback.status == "collection_error" and fallback.collection_errors == ["tests/test_x.py"]
    assert not g.classify_pytest(0, "").caught_bug


def test_parse_ruff_json(tmp_path):
    raw = json.dumps([{"code": "AIR301", "filename": str(tmp_path.resolve() / "dags" / "a.py"),
                       "location": {"row": 3, "column": 1}, "message": "removed"}])
    assert g.parse_ruff_json(raw, tmp_path) == [
        {"code": "AIR301", "filename": "dags/a.py", "line": 3, "message": "removed"}]
    assert g.parse_ruff_json("", tmp_path) == []


def test_air_select_for():
    assert g.air_select_for("2.11.2") == "AIR0,AIR2"
    assert g.air_select_for("3.3.2") == "AIR"
    assert g.air_select_for(None) == "AIR"


def test_deprecation_warnings_filters_workspace():
    imp = {"warnings": [
        {"category": "DeprecatedImportWarning", "message": "m", "filename": "dags/a.py", "lineno": 1},
        {"category": "RemovedInAirflow3Warning", "message": "m", "filename": "/venv/airflow/x.py", "lineno": 2},
        {"category": "UserWarning", "message": "m", "filename": "dags/a.py", "lineno": 3},
    ]}
    assert [w["lineno"] for w in g.deprecation_warnings(imp)] == [1]
    assert [w["lineno"] for w in g.deprecation_warnings(imp, workspace_only=False)] == [1, 2]


def test_parse_probe_output():
    out = "noise\n__EVAL_PROBE_RESULT__{\"a\": 1}\nmore noise\n"
    assert g.parse_probe_output(out) == {"a": 1}
    assert g.parse_probe_output("nothing") is None
    assert g.parse_probe_output("__EVAL_PROBE_RESULT__{bad") is None


def test_scrubbed_environ_and_airflow_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRFLOW__CORE__DAGS_FOLDER", "/elsewhere")
    monkeypatch.setenv("AIRFLOW_VAR_SECRET", "x")
    monkeypatch.setenv("AIRFLOW_HOME", "/elsewhere")
    monkeypatch.setenv("KEEP_ME", "1")
    clean = g.scrubbed_environ()
    assert "AIRFLOW_VAR_SECRET" not in clean and "AIRFLOW_HOME" not in clean and clean["KEEP_ME"] == "1"
    env = g.airflow_env(tmp_path, extra={"AIRFLOW_VAR_X": "y"}, airflow_home=tmp_path / "home",
                        env_py="/venv/bin/python")
    assert env["AIRFLOW__CORE__DAGS_FOLDER"] == str(tmp_path.resolve() / "dags")
    assert env["AIRFLOW_HOME"] == str(tmp_path / "home")
    assert env["AIRFLOW__CORE__LOAD_EXAMPLES"] == "False"
    assert env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] == "YES" and env["no_proxy"] == "*"
    assert env["PATH"].startswith("/venv/bin")
    assert env["AIRFLOW_VAR_X"] == "y" and "AIRFLOW_VAR_SECRET" not in env
    other = g.airflow_env(tmp_path)
    assert other["AIRFLOW_HOME"] != env["AIRFLOW_HOME"]


def test_env_python(monkeypatch, tmp_path):
    monkeypatch.setenv("EVAL_ENV_ROOT", str(tmp_path))
    assert g.env_python("3.3") == str(tmp_path / "airflow-3.3" / "bin" / "python")
    assert g.env_python("2.11").endswith("airflow-2.11/bin/python")
    with pytest.raises(ValueError):
        g.env_python("1.10")


def test_apply_overlay_and_copy_workspace(tmp_path):
    ws = tmp_path / "ws"
    (ws / "dags").mkdir(parents=True)
    (ws / "dags" / "a.py").write_text("a")
    (ws / "dags" / "old.py").write_text("old")
    (ws / ".git").mkdir()
    (ws / "dags" / "__pycache__").mkdir()
    ov = tmp_path / "ov"
    (ov / "dags").mkdir(parents=True)
    (ov / "dags" / "a.py").write_text("A")
    (ov / "tests").mkdir()
    (ov / "tests" / "t.py").write_text("t")
    (ov / "_DELETE").write_text("# comment\ndags/old.py\n")
    copy = g.copy_workspace(ws, [ov])
    assert (copy / "dags" / "a.py").read_text() == "A"
    assert (copy / "tests" / "t.py").read_text() == "t"
    assert not (copy / "dags" / "old.py").exists()
    assert not (copy / ".git").exists() and not (copy / "dags" / "__pycache__").exists()
    assert not (copy / "_DELETE").exists()
    assert (ws / "dags" / "a.py").read_text() == "a"  # source untouched


def test_apply_overlay_rejects_escape(tmp_path):
    ov = tmp_path / "ov"
    ov.mkdir()
    (ov / "_DELETE").write_text("../outside\n")
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(ValueError):
        g.apply_overlay(ov, dest)


def test_parse_args(tmp_path):
    ns = g.parse_args(["--workspace", str(tmp_path), "--out", str(tmp_path / "r.json")])
    assert ns.workspace == tmp_path.resolve() and ns.events is None


def test_dag_test_result_unpacks():
    r = g.DagTestResult(True, 0, False, "log", [{"tasks": {"a": "success", "b": "failed", "c": "upstream_failed"}}])
    ok, log = r
    assert ok and log == "log"
    assert r.failed_tasks() == ["b", "c"]


def test_run_cmd_timeout_kills_group():
    res = g.run_cmd(["sh", "-c", "sleep 30 & sleep 30"], timeout=1)
    assert res.timed_out and not res.ok
    assert g.run_cmd(["sh", "-c", "echo hi; echo err >&2"]).output.split() == ["hi", "err"]


SONNET46 = "google-vertex-anthropic/claude-sonnet-4-6@default"
# Real altimate-code 0.12.2 Vertex Sonnet 4.6 step: input includes the cached prompt.
DOUBLED = {"cost": 0.2155707, "tokens": {"input": 64049, "output": 190, "reasoning": 0,
                                        "cache": {"read": 63654, "write": 394}}}


def test_model_key_and_pricing():
    assert g.model_key("google-vertex-anthropic/claude-haiku-4-5@20251001") == "claude-haiku-4-5"
    assert g.model_key("anthropic/claude-haiku-4-5-20251001") == "claude-haiku-4-5"
    assert g.model_key("google-vertex-anthropic/claude-fable-5-1@default") == "claude-fable-5-1"
    assert g.model_pricing("google-vertex-anthropic/claude-opus-5-5@default") == (4.0, 20.0, 0.20, 5.00)
    assert g.model_pricing("google-vertex-anthropic/claude-sonnet-5-5@default")[:2] == (2.0, 10.0)
    assert g.model_pricing("x/unknown") is None


def test_cache_correction_gate():
    assert g.cache_correction_applies(SONNET46, "0.12.2")
    assert not g.cache_correction_applies(SONNET46, "0.13.0")
    assert not g.cache_correction_applies("anthropic/claude-sonnet-4-6", "0.12.2")
    assert not g.cache_correction_applies(SONNET46, None)


def test_step_cost_removes_cached_double_count():
    assert g.step_double_counted(DOUBLED, SONNET46) is True
    fixed = (1 * 3 + 190 * 15 + 63654 * 0.3 + 394 * 3.75) / 1e6
    assert g.step_cost(DOUBLED, SONNET46) == pytest.approx(fixed, rel=1e-9)
    # Unknown model: the ratio fallback gives about the same answer.
    assert g.step_cost(DOUBLED) == pytest.approx(0.0234, abs=5e-4)
    # Gate off (other provider/version): reported cost kept.
    assert g.step_cost(DOUBLED, SONNET46, correct=False) == pytest.approx(0.2155707)
    # No cache info, or input smaller than cached tokens: reported cost kept.
    assert g.step_cost({"cost": 0.5, "tokens": {"input": 80, "output": 20}}, SONNET46) == 0.5
    assert g.step_cost({"cost": 0.5, "tokens": {"input": 10, "cache": {"read": 100}}}, SONNET46) == 0.5


def test_step_cost_keeps_reported_when_model_does_not_double_count():
    # Same tokens, but the reported cost already excludes the cached part (as a fixed
    # provider would report it): the pricing check sees no double count and keeps it.
    model = "google-vertex-anthropic/claude-opus-5-5@default"
    part = {"cost": 0.0185, "tokens": {"input": 64049, "output": 190, "cache": {"read": 63654, "write": 394}}}
    assert g.step_double_counted(part, model) is False
    assert g.step_cost(part, model) == 0.0185
    doubled = dict(part, cost=g.list_price_cost(part, model, input_includes_cache=False))
    assert g.step_double_counted(doubled, model) is True
    assert g.step_cost(doubled, model) == pytest.approx(g.list_price_cost(part, model, True))


def test_usage_reports_audit_fields():
    u = g.usage([{"type": "step_finish", "part": DOUBLED}], SONNET46, correct=True)
    assert u["cost_reported_usd"] == pytest.approx(0.2155707, abs=1e-6) and u["cost_usd"] < 0.03
    assert u["double_counted_steps"] == 1 and u["cost_list_price_usd"] == pytest.approx(u["cost_usd"], rel=1e-6)
    off = g.usage([{"type": "step_finish", "part": DOUBLED}], SONNET46, correct=False)
    assert off["cost_usd"] == pytest.approx(0.2155707, abs=1e-6) and off["double_counted_steps"] == 1
    assert g.usage([], "x/unknown")["cost_list_price_usd"] is None


def test_agent_env_python(monkeypatch, tmp_path):
    monkeypatch.setenv("EVAL_ENV_ROOT", str(tmp_path))
    assert g.agent_env_python("3.3") == str(tmp_path / "agent-airflow-3.3" / "bin" / "python")
    assert g.agent_env_python("2.11") != g.env_python("2.11")
    with pytest.raises(ValueError):
        g.agent_env_python("1.10")
