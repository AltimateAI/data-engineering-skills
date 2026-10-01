"""Replay comparison unit tests and manual-run checks against available Airflow envs."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_airflow_check import clean_environ, env_python

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "skills" / "airflow" / "migrating-to-airflow-3" / "scripts" / "replay_compare.py"

spec = importlib.util.spec_from_file_location("replay_compare", SCRIPT)
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)


def _run(day, kind="scheduled", state="success", logical=None):
    return {"kind": kind, "run_after": day, "logical_date": logical or day, "state": state,
            "data_interval_start": logical or day, "data_interval_end": day}


def test_read_plan_skips_comments_and_keeps_quoted_conf(tmp_path):
    plan = tmp_path / "plan.txt"
    plan.write_text("# producers first\n\nload --runs 3 --from 2026-03-02\n"
                    "reprocess --runs 0 --manual 2026-03-05T09:00:00Z --conf '{\"day\": \"2026-03-03\"}'\n")
    assert rc.read_plan(str(plan)) == [
        ("load", ["--runs", "3", "--from", "2026-03-02"]),
        ("reprocess", ["--runs", "0", "--manual", "2026-03-05T09:00:00Z", "--conf", '{"day": "2026-03-03"}']),
    ]


def test_compare_runs_flags_date_shift_and_after_failure_but_not_manual_dates():
    before = {"runs": {"d": [_run("2026-03-03T00:00", logical="2026-03-02T00:00"),
                             _run("2026-03-05T09:00", kind="manual", logical="2026-03-05T09:00")]}}
    after = {"runs": {"d": [_run("2026-03-03T00:00", logical="2026-03-03T00:00"),
                            _run("2026-03-05T09:00", kind="manual", state="failed", logical=None)]}}
    diffs, notes = rc.compare_runs(before, after, legacy=False)
    assert any("logical_date" in d for d in diffs)
    assert any("manual@" in d and "AFTER run failed" in d for d in diffs)
    assert not any("manual@" in d and "logical_date" in d for d in diffs)
    assert notes == []


def test_legacy_mode_reports_missing_baseline_as_note():
    before = {"runs": {"d": [_run("2026-03-03T00:00", state="failed")]}}
    after = {"runs": {"d": [_run("2026-03-03T00:00"), _run("2026-03-04T00:00")]}}
    diffs, notes = rc.compare_runs(before, after, legacy=True)
    assert diffs == []
    assert len(notes) == 2


@pytest.mark.parametrize("legacy", [False, True])
def test_failed_manual_before_run_has_one_missing_baseline_note(legacy):
    before = {"runs": {"d": [_run("2026-03-05T09:00", kind="manual", state="failed")]}}
    after = {"runs": {"d": [_run("2026-03-05T09:00", kind="manual")]}}
    diffs, notes = rc.compare_runs(before, after, legacy=legacy)
    assert diffs == [] and len(notes) == 1
    assert "no baseline" in notes[0]


def test_legacy_manual_run_returns_unproven(tmp_path, monkeypatch, capsys):
    for side in ("before", "after"):
        (tmp_path / side / "dags").mkdir(parents=True)
    plan = tmp_path / "plan.txt"
    plan.write_text("d --runs 0 --manual 2026-03-05T09:00:00Z\n")
    monkeypatch.setattr(rc, "side_env", lambda *_: {})
    monkeypatch.setattr(rc, "replay_side", lambda name, *_: {
        "name": name, "runs": {"d": [_run("2026-03-05T09:00:00Z", kind="manual")]}, "errors": []})
    code = rc.main(["--before", str(tmp_path / "before"), "--after", str(tmp_path / "after"),
                    "--plan", str(plan), "--legacy-before"])
    output = capsys.readouterr().out
    assert code == rc.EXIT_UNPROVEN
    assert "No baseline" in output and "IDENTICAL:" not in output
    assert json.loads(output.splitlines()[-1])["no_baseline"] == 1


@pytest.mark.parametrize("baseline", ["legacy", "2.11"])
def test_real_manual_replay_requires_a_2x_baseline(tmp_path, baseline):
    python3 = env_python("3.3")
    before_flags = ["--legacy-before"] if baseline == "legacy" else ["--before-python", env_python("2.11")]
    for side in ("before", "after"):
        dags = tmp_path / side / "dags"
        dags.mkdir(parents=True)
        (dags / "probe.py").write_text(
            "import pendulum\nfrom airflow import DAG\n"
            "from airflow.operators.empty import EmptyOperator\n"
            "with DAG('manual_probe', schedule=None, "
            "start_date=pendulum.datetime(2026, 3, 1, tz='UTC')):\n"
            "    EmptyOperator(task_id='step')\n"
        )
    plan = tmp_path / "plan.txt"
    plan.write_text("manual_probe --runs 0 --manual 2026-03-05T09:00:00Z\n")
    proc = subprocess.run(
        [python3, str(SCRIPT), "--before", str(tmp_path / "before"), "--after", str(tmp_path / "after"),
         "--plan", str(plan), *before_flags], cwd=tmp_path,
        env=clean_environ(TMPDIR=str(tmp_path)), capture_output=True, text=True, timeout=180,
    )
    summary = json.loads(proc.stdout.splitlines()[-1])
    assert summary["errors"] == 0, proc.stdout + proc.stderr
    assert proc.returncode == (rc.EXIT_UNPROVEN if baseline == "legacy" else rc.EXIT_OK), proc.stdout
    assert summary["no_baseline"] == (1 if baseline == "legacy" else 0)


def test_compare_files_missing_changed_extra(tmp_path):
    b, a = tmp_path / "b", tmp_path / "a"
    for root in (b, a):
        (root / "output").mkdir(parents=True)
    (b / "output" / "same.csv").write_text("x\n")
    (a / "output" / "same.csv").write_text("x\n")
    (b / "output" / "gone.csv").write_text("x\n")
    (b / "output" / "chg.csv").write_text("1\n")
    (a / "output" / "chg.csv").write_text("2\n")
    (a / "output" / "new.csv").write_text("x\n")
    notes: list[str] = []
    diffs = rc.compare_files(b, a, ["output"], legacy=False, notes=notes)
    heads = [d for d in diffs if not d.startswith("    ")]
    assert heads == ["changed: output/chg.csv", "missing in AFTER: output/gone.csv", "extra in AFTER: output/new.csv"]
    legacy_notes: list[str] = []
    legacy = rc.compare_files(b, a, ["output"], legacy=True, notes=legacy_notes)
    assert "extra in AFTER: output/new.csv" not in legacy and legacy_notes


def test_usage_error_exit_3(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPT), "--before", str(tmp_path), "--after", str(tmp_path),
                           "--plan", str(tmp_path / "missing.txt")], capture_output=True, text=True)
    assert proc.returncode == 3
    assert "dags/" in proc.stderr


def test_read_plan_keeps_hash_inside_values_and_rejects_bad_quotes(tmp_path):
    plan = tmp_path / "plan.txt"
    plan.write_text("load --var token=abc#def --conf '{\"a\": \"a#b\"}'  # trailing comment\n")
    assert rc.read_plan(str(plan)) == [("load", ["--var", "token=abc#def", "--conf", '{"a": "a#b"}'])]
    plan.write_text("load --conf '{\"a\n")
    try:
        rc.read_plan(str(plan))
    except rc.UsageError as exc:
        assert "plan line 1" in str(exc)
    else:
        raise AssertionError("unbalanced quote accepted")


def test_repeated_runs_are_all_compared():
    failed_first = [_run("2026-03-03T00:00", kind="rerun", state="failed"),
                    _run("2026-03-03T00:00", kind="rerun")]
    ok = [_run("2026-03-03T00:00", kind="rerun"), _run("2026-03-03T00:00", kind="rerun")]
    diffs, _ = rc.compare_runs({"runs": {"d": ok}}, {"runs": {"d": failed_first}}, legacy=False)
    assert any("AFTER run failed" in d for d in diffs)


def test_outputs_outside_the_copy_are_rejected(tmp_path):
    for side in ("b", "a"):
        (tmp_path / side / "dags").mkdir(parents=True)
    (tmp_path / "keep").mkdir()
    plan = tmp_path / "plan.txt"
    plan.write_text("d --runs 1\n")
    for bad in ("../keep", ".", str(tmp_path / "keep")):
        code = rc.main(["--before", str(tmp_path / "b"), "--after", str(tmp_path / "a"),
                        "--plan", str(plan), "--outputs", bad])
        assert code == rc.EXIT_USAGE
    assert (tmp_path / "keep").is_dir() and (tmp_path / "b" / "dags").is_dir()
