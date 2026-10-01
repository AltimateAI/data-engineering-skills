"""Unit tests for evals/harness/rescore_contamination.py (synthetic altimate-code streams)."""

import json

import rescore_contamination as rc
import run_eval as re_

CASE = "migration-weekly-catchup"


def tool(cmd=None, ts=0, name="bash", output="", **inp):
    if cmd is not None:
        inp["command"] = cmd
    return {"type": "tool_use", "timestamp": ts,
            "part": {"tool": name, "state": {"status": "completed", "input": inp, "output": output}}}


def write_attempt(result_dir, case, model, run, events, status="ok", arm="skill", split="dev"):
    d = result_dir / "runs" / case / re_.slug(model) / f"run-{run}" / "attempt-0"
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    row = {"case": case, "arm": arm, "model": model, "run": str(run), "split": split, "area": "migration",
           "status": status, "primary_pass": status == "ok", "primary_score": 1.0 if status == "ok" else 0.0,
           "attempts": [{"attempt": 0, "status": status}]}
    with (result_dir / "runs.jsonl").open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def test_rescore_flags_and_grades_evidence(tmp_path):
    work = str(tmp_path / "work")
    camp = f"{work}/skill-x-skill-20260930-000000"
    own = f"{camp}/{CASE}-abc12345"
    res = tmp_path / "results" / "skill-x"
    res.mkdir(parents=True)
    (res / "meta.json").write_text(json.dumps({"arm": "skill"}))
    # run 1: writes its own /tmp file first (weak), uses a $$ temp dir (weak), mistypes its scratch (weak)
    write_attempt(res, CASE, "m", 1, [
        tool(f"cd {own}/ws && ls", ts=10),
        tool(f"echo hi > /tmp/summary.md && cat /tmp/summary.md", ts=11),
        tool(f"AIRFLOW_HOME=/tmp/af_$$ airflow db migrate", ts=12),
        tool(name="read", ts=13, filePath=f"{work}/skill-x-skill-2026-{CASE}-abc12345/ws/README.md"),
        tool(name="read", ts=14, filePath=f"{camp}/skills/airflow/x/SKILL.md"),
    ])
    # run 2: reuses /tmp/summary.md that run 1 wrote earlier, without overwriting it (strong)
    write_attempt(res, CASE, "m", 2, [
        tool(f"cd {camp}/{CASE}-zzz99999/ws && ls", ts=20),
        tool("cat /tmp/summary.md", ts=21),
    ], status="task_fail")
    # run 3: stays inside its scratch (clean)
    write_attempt(res, CASE, "m", 3, [tool(f"cd {camp}/{CASE}-qqq11111/ws && pytest", ts=30)])
    records, rows = rc.rescore([res], [res], work, str(tmp_path))
    by_run = {r["run"]: r for r in records}
    assert by_run["1"]["contamination_suspect"] is True and by_run["1"]["evidence_strength"] == "weak"
    access = {h["path"]: h["first_access"] for h in by_run["1"]["hits"]}
    assert access["/tmp/summary.md"] == "overwrite" and access["/tmp/af_"] == "generated"
    assert any(v == "own_scratch_mistyped" for k, v in access.items() if k.startswith(work))
    assert not any("skills/airflow" in k for k in access)  # staged skills are allowed
    assert by_run["2"]["evidence_strength"] == "strong"
    (hit,) = by_run["2"]["hits"]
    assert hit["n_prior_users"] == 1 and hit["first_access"] == "use"
    assert by_run["3"]["contamination_suspect"] is False and by_run["3"]["evidence_strength"] == "none"
    flags = {r["run"]: (r["contamination_suspect"], r["contamination_strong"]) for r in rows}
    assert flags == {"1": (True, False), "2": (True, True), "3": (False, False)}


def test_overwrite_must_be_first_reference_in_command():
    assert rc._overwrites({"tool": "bash", "input": {"command": "echo y > /tmp/x && cat /tmp/x"}}, "/tmp/x")
    assert not rc._overwrites({"tool": "bash", "input": {"command": "cat /tmp/x; echo y > /tmp/x"}}, "/tmp/x")
    assert not rc._overwrites({"tool": "bash", "input": {"command": "echo y >> /tmp/x"}}, "/tmp/x")
    assert rc._overwrites({"tool": "write", "input": {"filePath": "/tmp/x"}}, "/tmp/x")


def test_alias_spellings_and_hit_cap(tmp_path):
    work = "/tmp/eval-work"
    own = f"/private/tmp/eval-work/camp/{CASE}-own12345"
    calls = [tool(f"cd {own}/ws", ts=1), tool("echo a > /tmp/x", ts=2), tool("cat /private/tmp/x", ts=3)]
    calls += [tool(f"cat /tmp/f{i}", ts=10 + i) for i in range(60)]
    scan = rc.scan_attempt(calls, CASE, tmp_path, work, True, str(tmp_path))
    # the scratch dir is recognised through the /private alias, so it is not a hit
    assert scan["scratch"] and not any(h["root"] == "work-root" for h in scan["hits"])
    # the first spelling decides the access type for later alias spellings
    assert {h["first_access"] for h in scan["hits"] if h["key"] == "/tmp/x"} == {"overwrite"}
    # no 50-hit truncation
    assert len(scan["hits"]) == 62


def test_dedupe_keeps_scored_attempt_flags():
    clean = {"case": "c", "arm": "skill", "model": "m", "run": "1", "status": "ok", "attempts": [{"status": "ok"}],
             "_source": "b", "contamination_suspect": False, "contamination_strong": False,
             "_rescore_flags": (False, False)}
    paid = {"case": "c", "arm": "skill", "model": "m", "run": "1", "status": "skipped_budget", "cost_usd": 1.0,
            "attempts": [{"status": "infra_error"}], "_source": "a", "contamination_suspect": True,
            "contamination_strong": True, "_rescore_flags": (True, True)}
    (kept,) = rc.dedupe([paid, clean])
    assert kept["contamination_suspect"] is False and kept["contamination_strong"] is False


def test_main_writes_summary_and_both_tables(tmp_path):
    work = str(tmp_path / "work")
    out = tmp_path / "summary"
    dirs = []
    for arm in ("baseline", "skill"):
        res = tmp_path / "results" / arm
        res.mkdir(parents=True)
        (res / "meta.json").write_text(json.dumps({"arm": arm}))
        camp = f"{work}/{arm}-{arm}-20260930-000000"
        for run in (1, 2):
            dirty = arm == "skill" and run == 2
            evs = [tool(f"cd {camp}/{CASE}-r{run}{arm}/ws && ls", ts=run)]
            if dirty:
                evs.append(tool("cat /tmp/leftover.csv", ts=99))
            write_attempt(res, CASE, "m", run, evs, status="ok" if arm == "skill" else "task_fail", arm=arm)
        dirs.append(res)
    assert rc.main([*map(str, dirs), "--out", str(out), "--work-root", work, "--bootstrap", "200"]) == 0
    md = (out / "REPORT.md").read_text()
    assert "## Pass rate: All runs" in md and "## Pass rate: Excluding flagged runs" in md
    assert "## Per-case paired deltas" in md and "## Do conclusions change" in md
    top = json.loads((out / "results.json").read_text())
    assert set(top["tables"]) == {"all", "excluding-flagged", "excluding-strong"}
    assert top["tables"]["excluding-flagged"]["n_runs"] == 3
    (case_row,) = top["per_case_deltas"]
    assert case_row["all"]["delta_pass_rate"] == 1.0 and case_row["excluding-flagged"]["delta_pass_rate"] == 1.0
    assert {c["model"] for c in top["conclusion_check"]} == {"m", "pooled"}
    all_res = json.loads((out / "all" / "results.json").read_text())
    clean = json.loads((out / "excluding-flagged" / "results.json").read_text())
    assert all_res["n_runs"] == 4 and clean["n_runs"] == 3
    lines = [json.loads(x) for x in (out / "contamination.jsonl").read_text().splitlines()]
    assert sum(1 for x in lines if x["contamination_suspect"]) == 1
    assert "pooled_deltas" in clean


def test_conclusion_check_flags_sign_and_significance_changes():
    def res(delta, ci, pooled_ci):
        return {"paired_deltas": [{"split": "dev", "model": "m", "n_cases": 3, "mean_delta_pass_rate": delta,
                                   "ci95_delta_pass_rate": ci, "cases": []}],
                "pooled_deltas": [{"split": "dev", "n_cases": 3, "mean_delta_pass_rate": delta,
                                   "ci95_delta_pass_rate": pooled_ci}]}
    reports = {"all": res(0.4, (0.1, 0.7), (0.1, 0.7)), "excluding-flagged": res(0.3, (-0.1, 0.6), (0.05, 0.6))}
    model, pooled = rc.conclusion_check(reports)
    assert model["model"] == "m" and model["sign_same"] and not model["significance_same"] and model["changed"]
    assert pooled["model"] == "pooled" and not pooled["changed"]
