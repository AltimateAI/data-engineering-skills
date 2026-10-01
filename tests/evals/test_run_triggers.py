"""Unit tests for the pure parts of evals/harness/run_triggers.py (no LLM)."""

import json
import hashlib
from pathlib import Path

import pytest
import run_triggers as t

A, M, T = "authoring-airflow-dags", "migrating-to-airflow-3", "testing-airflow-dags"
NAMES = [A, M, T]
REPO = Path(__file__).resolve().parents[2]


def row(qid, expected, fired, model="m/sonnet", run=1, status="ran"):
    return {"query_id": qid, "context": "airflow3", "expected": expected, "query": f"q {qid}",
            "fired": fired, "model": model, "run": run, "status": status}


def test_fired_skills_dedupes_in_order():
    inv = [{"name": T}, {"name": "creating-dbt-models"}, {"name": T}, {"name": None}]
    assert t.fired_skills(inv, [A, T]) == [T, "creating-dbt-models", A]
    assert t.fired_skills([]) == []


@pytest.mark.parametrize("expected,fired,outcome", [
    (A, [A], "hit"),
    (A, ["creating-dbt-models", A], "hit"),
    (A, [A, T], "hit_plus"),
    (A, [M], "confused"),
    (A, ["creating-dbt-models"], "miss"),
    (A, [], "miss"),
    (None, [], "quiet"),
    (None, ["testing-dbt-models"], "quiet"),
    (None, [T], "false_fire"),
])
def test_classify_trigger(expected, fired, outcome):
    assert t.classify_trigger(expected, fired, NAMES) == outcome


def test_compute_metrics():
    rows = [
        row("a1", A, [A]), row("a2", A, []), row("a3", A, [A, T]), row("a4", A, [M]),
        row("m1", M, [M]), row("m2", M, [M]),
        row("t1", T, [T]), row("t2", T, [A]),
        row("n1", None, []), row("n2", None, [A]), row("n3", None, ["creating-dbt-models"]),
        row("n4", None, [A], status="infra_error"), row("n5", None, [], status="skipped_budget"),
    ]
    m = t.compute_metrics(rows, NAMES)
    assert m["scored_runs"] == 11
    assert m["unscored_runs"] == {"infra_error": 1, "skipped_budget": 1}
    a = m["per_skill"][A]
    assert (a["should_fire_runs"], a["fired_when_expected"], a["recall"]) == (4, 2, 0.5)
    # A fired in a1, a3, t2, n2 -> 2 of 4 expected A
    assert (a["runs_where_fired"], a["precision"]) == (4, 0.5)
    assert (a["wrong_airflow_skill_on_own_queries"], a["confusion_rate"]) == (2, 0.5)  # a3 (T), a4 (M)
    assert a["fired_on_other_airflow_queries"] == 1  # t2
    assert (a["near_miss_false_fires"], a["near_miss_false_fire_rate"]) == (1, 0.333)
    mm = m["per_skill"][M]
    assert (mm["recall"], mm["precision"], mm["confusion_rate"]) == (1.0, 0.667, 0.0)
    assert m["near_miss"] == {"runs": 3, "any_airflow_false_fires": 1, "false_fire_rate": 0.333}
    assert m["confusion_matrix"][A] == {A: 2, M: 1, T: 1, "(no airflow skill)": 1, "runs": 4}
    assert m["confusion_matrix"]["None"] == {A: 1, M: 0, T: 0, "(no airflow skill)": 2, "runs": 3}
    assert m["outcomes"] == {"hit": 4, "miss": 1, "hit_plus": 1, "confused": 2, "quiet": 2, "false_fire": 1}


def test_compute_metrics_empty_gives_none_ratios():
    m = t.compute_metrics([], NAMES)
    assert m["per_skill"][A]["recall"] is None and m["near_miss"]["false_fire_rate"] is None


def test_misfires_and_report():
    rows = [row("a1", A, [A]), row("a2", A, [M], model="m/haiku"), row("n1", None, [T]),
            row("n2", None, [], status="infra_error")]
    bad = t.notable_misfires(rows, NAMES)
    assert [(b["query_id"], b["outcome"]) for b in bad] == [("a2", "confused"), ("n1", "false_fire")]
    queries = [{"id": "a1", "expected": A}, {"id": "a2", "expected": A}, {"id": "n1", "expected": None},
               {"id": "n2", "expected": None}]
    s = t.build_summary(rows, NAMES, queries, ["m/sonnet", "m/haiku"], "demo",
                        {"runs_per_query": 1, "max_turns": 4, "airflow_skills_sha256": "abc",
                         "spent_usd": 1.5, "cap_usd": 40})
    assert s["n_should_fire"] == 2 and s["n_near_miss"] == 2
    assert s["by_model"]["m/haiku"]["per_skill"][A]["recall"] == 0.0
    pq = {q["query_id"]: q for q in s["per_query"]}
    assert pq["n2"]["runs"][0]["outcome"] is None
    md = t.render_report(s)
    assert "| authoring-airflow-dags | 1/2 (50%)" in md
    assert "**confused** `a2` (haiku run 1)" in md and '"q a2"' in md
    assert "Unscored runs" in md and "sha256: `abc`" in md


def test_short_model_and_trigger_caps():
    assert t._short_model("google-vertex-anthropic/claude-sonnet-5-5@default") == "sonnet-5-5"
    assert t._short_model("m/haiku") == "haiku"
    fable = "google-vertex-anthropic/claude-fable-5-1@default"
    assert t.trigger_run_cap(fable, {}, None) == round(t.TRIGGER_CAP_FRACTION * t.r.DEFAULT_RUN_CAP_USD[
        "claude-fable-5-1"], 2)
    assert t.trigger_run_cap(fable, {}, 1.5) == 1.5
    assert t.trigger_run_cap(fable, {"claude-fable-5-1": 9}, 1.5) == 9


def test_deactivate_airflow():
    env = {"PATH": "/venv/bin:/usr/bin", "VIRTUAL_ENV": "/venv", "AIRFLOW_HOME": "/x",
           "AIRFLOW__CORE__DAGS_FOLDER": "/y", "OPENCODE_TEST_HOME": "/h"}
    out = t.deactivate_airflow(env, "/venv/bin/python")
    assert out == {"PATH": "/usr/bin", "OPENCODE_TEST_HOME": "/h"}
    assert env["VIRTUAL_ENV"] == "/venv"  # input not mutated


def write_queries(tmp_path, queries, contexts=None):
    (tmp_path / "fx").mkdir(exist_ok=True)
    data = {"contexts": contexts or {"af": {"fixture": "fx", "airflow_version": "3.3"},
                                     "py": {"fixture": "fx", "airflow_version": None}},
            "queries": queries}
    p = tmp_path / "queries.json"
    p.write_text(json.dumps(data))
    return p


def test_load_queries_ok(tmp_path):
    p = write_queries(tmp_path, [{"id": "a", "context": "af", "expected": A, "query": "x"},
                                 {"id": "n", "context": "py", "expected": None, "query": "y"}])
    ctx, qs = t.load_queries(p, NAMES)
    assert ctx["af"]["fixture"] == (tmp_path / "fx").resolve() and ctx["py"]["airflow_version"] is None
    assert [q["id"] for q in qs] == ["a", "n"]


def test_load_queries_problems(tmp_path):
    p = write_queries(
        tmp_path,
        [{"id": "a", "context": "nope", "expected": "bogus", "query": ""},
         {"id": "a", "context": "af", "query": "x"}],
        contexts={"af": {"fixture": "missing", "airflow_version": "2.10"}},
    )
    with pytest.raises(ValueError) as exc:
        t.load_queries(p, NAMES)
    msg = str(exc.value)
    for frag in ("not a directory", "airflow_version must be", "unknown context", "missing query text",
                 "not an airflow skill", "duplicate id", "missing expected"):
        assert frag in msg


def test_repo_queries_file_is_valid():
    """The shipped queries.json: ~6 should-fire per airflow skill plus near-misses."""
    names = t.r.skill_names(REPO / "skills/airflow")
    ctx, qs = t.load_queries(REPO / "evals/airflow/triggers/queries.json", names)
    for n in names:
        assert sum(1 for q in qs if q["expected"] == n) >= 5
    assert sum(1 for q in qs if q["expected"] is None) >= 10
    assert set(ctx) == {"airflow2", "airflow3", "dbt", "python"}


@pytest.mark.parametrize("changed", ["skills", "queries", "fixture"])
def test_resume_rejects_provenance_drift_before_launch(tmp_path, monkeypatch, changed):
    queries = write_queries(tmp_path, [{"id": "a", "context": "af", "expected": A, "query": "x"}])
    skills = tmp_path / "skills"
    skill = skills / A / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(f"---\nname: {A}\ndescription: original\n---\n")
    out = tmp_path / "results"
    out.mkdir()
    meta = {"runner": "altimate-code", "models": ["m"],
            "airflow_skills_sha256": t.r.hash_dir(skills),
            "queries_sha256": hashlib.sha256(queries.read_bytes()).hexdigest(),
            "fixtures_sha256": {n: t.r.hash_dir(tmp_path / "fx") for n in ("af", "py")}}
    (out / "meta.json").write_text(json.dumps(meta))
    (out / "runs.jsonl").write_text("\n")
    if changed == "skills":
        skill.write_text(skill.read_text().replace("original", "changed"))
    elif changed == "queries":
        queries.write_text(queries.read_text().replace('"query": "x"', '"query": "changed"'))
    else:
        (tmp_path / "fx" / "README.md").write_text("changed fixture")
    monkeypatch.setattr(t.r, "missing_interpreters", lambda *_: pytest.fail("resume must abort before launch setup"))
    assert t.main(["--resume", "--out", str(out), "--queries", str(queries),
                   "--skills-dir", str(skills), "--models", "m"]) == 2
    assert json.loads((out / "meta.json").read_text()) == meta
    assert (out / "runs.jsonl").read_text() == "\n"


def test_trigger_resume_accepts_matching_provenance():
    hashes = {"airflow_skills_sha256": "skills", "queries_sha256": "queries",
              "fixtures_sha256": {"af": "fixture"}}
    meta = {"runner": "claude-code", "models": ["m"], **hashes}
    assert t.resume_meta_problems(meta, "claude-code", ["m"], hashes) == []
    assert t.resume_meta_problems(meta, "altimate-code", ["m"], hashes)
    assert t.resume_meta_problems(meta, "claude-code", ["other"], hashes)
    assert t.resume_meta_problems({}, "claude-code", ["m"], hashes)
