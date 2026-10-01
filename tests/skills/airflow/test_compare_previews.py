"""Tests for skills/airflow/migrating-to-airflow-3/scripts/compare_previews.py (stdlib only)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "skills" / "airflow" / "migrating-to-airflow-3" / "scripts" / "compare_previews.py"

RUN = {"run_after": "2026-03-03T04:00:00+00:00", "logical_date": "2026-03-02T04:00:00+00:00",
       "data_interval_start": "2026-03-02T04:00:00+00:00",
       "data_interval_end": "2026-03-03T04:00:00+00:00"}


def dag(dag_id="daily", timetable="CronDataIntervalTimetable", runs=(RUN,), catchup=True, **kw):
    return {"dag_id": dag_id, "timetable": timetable, "catchup": catchup, "next_runs": list(runs),
            "warnings": [], **kw}


def report(*dags, import_errors=()):
    return {"dags": list(dags), "import_errors": list(import_errors)}


def compare(tmp_path, before, after, *args):
    b, a = tmp_path / "before.json", tmp_path / "after.json"
    b.write_text("log line before\n" + json.dumps(before) + "\n")
    a.write_text(json.dumps(after))
    proc = subprocess.run([sys.executable, str(SCRIPT), str(b), str(a), *args],
                          capture_output=True, text=True, timeout=60)
    return json.loads(proc.stdout), proc.returncode


def test_identical_previews_match(tmp_path):
    out, code = compare(tmp_path, report(dag()), report(dag()))
    assert code == 0 and out["summary"]["match"] == 1


def test_shifted_logical_date_differs(tmp_path):
    shifted = dict(RUN, logical_date=RUN["run_after"], data_interval_start=RUN["run_after"])
    out, code = compare(tmp_path, report(dag()), report(dag(timetable="CronTriggerTimetable",
                                                            runs=[shifted])))
    assert code == 2
    assert {d["field"] for d in out["dags"][0]["diffs"]} == {"logical_date", "data_interval_start"}


def test_catchup_change_differs(tmp_path):
    _, code = compare(tmp_path, report(dag()), report(dag(catchup=False)))
    assert code == 2


@pytest.mark.parametrize("before,after", [
    (report(import_errors=[{"file": "a.py"}]), report(import_errors=[{"file": "a.py"}])),
    (report(dag(), import_errors=[{"file": "b.py"}]), report(dag())),
    (report(), report()),
])
def test_incomplete_previews_are_not_a_match(tmp_path, before, after):
    out, code = compare(tmp_path, before, after)
    assert code == 2 and out["summary"]["problems"]


def test_failed_preview_is_not_a_match(tmp_path):
    failed = dag(runs=[], warnings=["could not preview runs: ValueError: boom"])
    out, code = compare(tmp_path, report(failed), report(failed))
    assert code == 2 and out["dags"][0]["status"] == "differs"


def test_unscheduled_dag_without_runs_matches(tmp_path):
    manual = dag(timetable="NullTimetable", runs=[])
    _, code = compare(tmp_path, report(manual), report(manual))
    assert code == 0


def test_requested_dag_missing_everywhere_is_reported(tmp_path):
    out, code = compare(tmp_path, report(dag()), report(dag()), "--dag-id", "daily",
                        "--dag-id", "missing")
    assert code == 2
    assert {r["dag_id"]: r["status"] for r in out["dags"]} == {"daily": "match",
                                                              "missing": "missing_both"}


def test_malformed_report_is_usage_error(tmp_path):
    _, code = compare(tmp_path, {"dags": [{"timetable": "x"}]}, report(dag()))
    assert code == 3
