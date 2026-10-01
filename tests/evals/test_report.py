"""Unit tests for evals/harness/report.py."""

import json

import pytest
import report as rp


def row(case, arm, passed, status=None, split="dev", model="m", score=None, skills=(), cost=1.0):
    return {"case": case, "arm": arm, "model": model, "split": split, "area": "authoring",
            "status": status or ("ok" if passed else "task_fail"), "primary_pass": passed,
            "primary_score": score if score is not None else (1.0 if passed else 0.5),
            "secondary_score": 0.5, "airflow_skills_used": list(skills), "cost_usd": cost,
            "tokens": {"total": 10, "input": 8, "output": 2}, "wall_s": 3.0, "retries": 0}


def test_group_stats_excludes_invalid():
    st = rp.group_stats([row("c", "skill", True, skills=["s1"]), row("c", "skill", False),
                         row("c", "skill", False, status="infra_error"),
                         row("c", "skill", False, status="grader_error")])
    assert st["n_runs"] == 4 and st["n_valid"] == 2 and st["n_excluded"] == 2
    assert st["pass_rate"] == 0.5 and st["trigger_rate"] == 0.5
    assert st["skills_used"] == {"s1": 1}
    assert st["total_cost_usd"] == 4.0 and st["mean_cost_usd"] == 1.0
    assert st["statuses"] == {"ok": 1, "task_fail": 1, "infra_error": 1, "grader_error": 1}


def test_group_stats_all_invalid():
    st = rp.group_stats([row("c", "skill", False, status="infra_error")])
    assert st["pass_rate"] is None and st["n_valid"] == 0


def test_bootstrap_ci():
    assert rp.bootstrap_ci([]) == (None, None)
    assert rp.bootstrap_ci([0.5]) == (0.5, 0.5)
    lo, hi = rp.bootstrap_ci([0.0, 1.0, 0.0, 1.0, 1.0], iters=2000, seed=1)
    assert 0.0 <= lo <= 0.6 <= hi <= 1.0
    assert rp.bootstrap_ci([0.3] * 5) == (0.3, 0.3)
    assert rp.bootstrap_ci([0.0, 1.0], seed=3) == rp.bootstrap_ci([0.0, 1.0], seed=3)


def test_aggregate_paired_deltas_by_split():
    rows = [
        row("a", "baseline", False), row("a", "baseline", False), row("a", "skill", True), row("a", "skill", True),
        row("b", "baseline", True), row("b", "skill", True),
        row("h", "baseline", True, split="holdout"), row("h", "skill", False, split="holdout"),
        row("only_base", "baseline", True),
    ]
    res = rp.aggregate(rows, iters=500)
    deltas = {(d["model"], d["split"]): d for d in res["paired_deltas"]}
    dev = deltas[("m", "dev")]
    assert dev["n_cases"] == 2 and dev["mean_delta_pass_rate"] == 0.5
    assert {c["case"] for c in dev["cases"]} == {"a", "b"}
    assert deltas[("m", "holdout")]["mean_delta_pass_rate"] == -1.0
    assert res["failure_classes"]["ok"] == 6
    md = rp.render_markdown({**res, "sources": []})
    assert "## dev: paired delta" in md and "## holdout: per case" in md


def test_cluster_bootstrap_ci_resamples_whole_cases():
    assert rp.cluster_bootstrap_ci([]) == (None, None)
    # One case with two models: resampling cases cannot separate its models, so the
    # CI collapses to the pooled mean. Resampling (case, model) pairs would not.
    assert rp.cluster_bootstrap_ci([[0.0, 1.0]]) == (0.5, 0.5)
    assert rp.bootstrap_ci([0.0, 1.0], iters=2000) == (0.0, 1.0)
    # Clusters of unequal size: the statistic is the mean over all carried values.
    lo, hi = rp.cluster_bootstrap_ci([[1.0, 1.0, 1.0], [0.0]], iters=4000, seed=2)
    assert lo == 0.0 and hi == 1.0
    assert rp.cluster_bootstrap_ci([[0.2, 0.4], [0.3]], seed=5) == rp.cluster_bootstrap_ci([[0.2, 0.4], [0.3]], seed=5)


def test_pooled_delta_clusters_models_by_case():
    # Case a: both models gain +1; case b: both models 0. Within-case results are
    # perfectly correlated, so the pooled CI must match a 2-case bootstrap of the
    # per-case means, not a 4-pair bootstrap.
    rows = []
    for model in ("m1", "m2"):
        rows += [row("a", "baseline", False, model=model), row("a", "skill", True, model=model),
                 row("b", "baseline", True, model=model), row("b", "skill", True, model=model)]
    res = rp.aggregate(rows, iters=4000, seed=7)
    (pooled,) = res["pooled_deltas"]
    assert pooled["split"] == "dev" and pooled["n_cases"] == 2 and pooled["n_pairs"] == 4
    assert pooled["mean_delta_pass_rate"] == 0.5
    assert pooled["ci95_delta_pass_rate"] == rp.bootstrap_ci([1.0, 0.0], iters=4000, seed=7)
    assert pooled["models"] == ["m1", "m2"]
    md = rp.render_markdown({**res, "sources": []})
    assert "pooled (4 case x model pairs)" in md


def test_main_writes_outputs(tmp_path):
    d = tmp_path / "run"
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({"arm": "baseline", "models": ["m"]}))
    (d / "runs.jsonl").write_text(json.dumps(row("a", "baseline", True)) + "\n")
    out = tmp_path / "out"
    assert rp.main([str(d), "--out", str(out), "--bootstrap", "100"]) == 0
    res = json.loads((out / "results.json").read_text())
    assert res["groups"][0]["pass_rate"] == 1.0
    assert (out / "REPORT.md").read_text().startswith("# Airflow skill eval report")
    with pytest.raises(SystemExit):
        rp.main([str(tmp_path / "empty"), "--out", str(out)])


def test_dedupe_runs_placeholder_replaced_and_collision(tmp_path):
    first = [dict(row("a", "baseline", True), run=1, _source="d1"),
             dict(row("a", "baseline", False, status="skipped_budget"), run=3, _source="d1")]
    second = [dict(row("a", "baseline", True), run=3, _source="d2")]
    kept, dropped = rp.dedupe_runs(first + second)
    assert sorted((r["run"], r["_source"]) for r in kept) == [(1, "d1"), (3, "d2")]
    assert [(r["run"], r["status"]) for r in dropped] == [(3, "skipped_budget")]
    # Placeholder alone (no follow-up) is kept.
    kept, dropped = rp.dedupe_runs(first)
    assert len(kept) == 2 and not dropped
    with pytest.raises(SystemExit, match="duplicate launched runs"):
        rp.dedupe_runs(first + second + [dict(row("a", "baseline", False), run=3, _source="d3")])


def test_main_merges_offset_campaign(tmp_path):
    d1, d2 = tmp_path / "d1", tmp_path / "d2"
    for d, rows in ((d1, [dict(row("a", "baseline", True), run=1), dict(row("a", "baseline", False), run=2),
                          dict(row("a", "baseline", False, status="skipped_budget", cost=0.0), run=3)]),
                    (d2, [dict(row("a", "baseline", True), run=3)])):
        d.mkdir()
        (d / "meta.json").write_text(json.dumps({"arm": "baseline"}))
        (d / "runs.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
    out = tmp_path / "out"
    assert rp.main([str(d1), str(d2), "--out", str(out), "--bootstrap", "100"]) == 0
    res = json.loads((out / "results.json").read_text())
    g = res["groups"][0]
    assert (g["n_runs"], g["n_valid"], g["n_excluded"]) == (3, 3, 0)
    assert abs(g["pass_rate"] - 2 / 3) < 1e-3 and g["statuses"] == {"ok": 2, "task_fail": 1}
    assert len(res["superseded_placeholders"]) == 1


def test_dedupe_keeps_spend_of_paid_placeholder():
    """infra attempts ($1.25) then skipped_budget, replaced by a $0.75 launched run: $2.00 total."""
    paid = dict(row("a", "baseline", False, status="skipped_budget", cost=1.25), run=3, _source="d1",
                attempts=[{"status": "infra_error", "cost_usd": 0.6, "launched": True},
                          {"status": "infra_error", "cost_usd": 0.65, "launched": True},
                          {"status": "skipped_budget", "cost_usd": 0.0}])
    unpaid = dict(row("a", "baseline", False, status="skipped_budget", cost=0.0), run=3, _source="d0",
                  attempts=[{"status": "skipped_budget", "cost_usd": 0.0}])
    launched = dict(row("a", "baseline", True, cost=0.75), run=3, _source="d2", retries=0)
    kept, dropped = rp.dedupe_runs([unpaid, paid, launched])
    assert len(kept) == 1 and kept[0]["status"] == "ok"
    assert kept[0]["cost_usd"] == 2.0 and kept[0]["superseded_cost_usd"] == 1.25
    assert kept[0]["retries"] == 2 and kept[0]["merged_from"] == ["d1"]
    assert len(dropped) == 2
    st = rp.group_stats(kept)
    assert st["total_cost_usd"] == 2.0 and st["mean_cost_usd"] == 2.0
    assert [a.get("superseded_from") for a in kept[0]["attempts"]] == ["d1", "d1"]


def test_dedupe_keeps_contamination_of_superseded_row():
    paid = dict(row("a", "skill", False, status="skipped_budget", cost=0.5), run=1, _source="d1",
                contamination_suspect=True, attempts=[{"status": "infra_error", "cost_usd": 0.5, "launched": True}])
    launched = dict(row("a", "skill", True, cost=1.0), run=1, _source="d2")
    kept, _ = rp.dedupe_runs([paid, launched])
    assert kept[0]["contamination_suspect"] is True and kept[0]["cost_usd"] == 1.5


def test_consistency_flags_different_staged_skills():
    metas = [{"dir": "d1", "arm": "baseline", "staged_skills_sha256": "a"},
             {"dir": "d2", "arm": "baseline", "staged_skills_sha256": "b"},
             {"dir": "d3", "arm": "skill", "staged_skills_sha256": "c"}]
    problems = rp.check_consistency(metas, [])
    assert len(problems) == 1 and "baseline arm dirs staged different skill sets" in problems[0]


def _write_dir(d, rows, meta):
    d.mkdir()
    (d / "meta.json").write_text(json.dumps(meta))
    (d / "runs.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))


def test_merge_rejects_conflicting_case_metadata(tmp_path):
    case_a = {"sha256": "h1", "split": "dev", "area": "authoring", "airflow_version": "3.3"}
    _write_dir(tmp_path / "d1", [dict(row("a", "skill", True), run=1)],
               {"arm": "skill", "airflow_skills_sha256": "s1", "cases": {"a": case_a}})
    _write_dir(tmp_path / "d2", [dict(row("a", "skill", True, split="holdout"), run=2)],
               {"arm": "skill", "airflow_skills_sha256": "s2", "cases": {"a": dict(case_a, sha256="h2",
                                                                                   split="holdout")}})
    out = tmp_path / "out"
    with pytest.raises(SystemExit, match="disagree"):
        rp.main([str(tmp_path / "d1"), str(tmp_path / "d2"), "--out", str(out), "--bootstrap", "10"])
    rows, metas = rp.load_rows([tmp_path / "d1", tmp_path / "d2"])
    problems = rp.check_consistency(metas, rows)
    assert any("conflicting sha256" in p for p in problems)
    assert any("conflicting split" in p for p in problems)
    assert any("skills/airflow revisions" in p for p in problems)
    assert rp.main([str(tmp_path / "d1"), str(tmp_path / "d2"), "--out", str(out), "--bootstrap", "10",
                    "--allow-mixed"]) == 0
    res = json.loads((out / "results.json").read_text())
    assert res["consistency_warnings"] and "--allow-mixed" in (out / "REPORT.md").read_text()


def test_consistent_dirs_merge_and_report_isolation(tmp_path):
    case_a = {"sha256": "h1", "split": "dev", "area": "authoring", "airflow_version": "3.3"}
    sus = dict(row("a", "baseline", False), run=1, contamination_suspect=True, agent_env_restored=True,
               attempts=[{"status": "task_fail", "isolation": {"hits": [{"tool": "bash", "path": "/tmp/x",
                                                                          "root": "shared-temp"}]}}])
    _write_dir(tmp_path / "d1", [sus], {"arm": "baseline", "cases": {"a": case_a}})
    _write_dir(tmp_path / "d2", [dict(row("a", "baseline", True), run=2)], {"arm": "baseline",
                                                                           "cases": {"a": case_a}})
    out = tmp_path / "out"
    assert rp.main([str(tmp_path / "d1"), str(tmp_path / "d2"), "--out", str(out), "--bootstrap", "10"]) == 0
    res = json.loads((out / "results.json").read_text())
    assert res["total_cost_usd"] == 2.0 and len(res["isolation"]["contamination_suspects"]) == 1
    md = (out / "REPORT.md").read_text()
    assert "Contamination suspects: 1 run(s)" in md and "bash:<tmp>/x (shared-temp)" in md
    assert "Agent env restored after: 1 run(s)" in md
