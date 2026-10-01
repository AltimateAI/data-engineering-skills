"""Tests for skills/airflow/_shared/replay_runs.py (consecutive runs in one metadata DB)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from test_airflow_check import clean_environ, env_python

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "skills" / "airflow" / "_shared" / "replay_runs.py"

STATEFUL_3X = '''
import json
import pendulum
from airflow.sdk import dag, task, Variable, get_current_context, CronDataIntervalTimetable


@dag(schedule=CronDataIntervalTimetable("0 4 * * *", timezone="UTC"),
     start_date=pendulum.datetime(2026, 3, 1, tz="UTC"), catchup=False)
def stateful():
    @task
    def step():
        ctx = get_current_context()
        ti, dr = ctx["ti"], ctx["dag_run"]
        counter = int(Variable.get("counter", default="0")) + 1
        Variable.set("counter", str(counter))
        prior = ti.xcom_pull(task_ids="step", key="mark", include_prior_dates=True)
        with open(OUT, "a") as fh:
            fh.write(json.dumps({"run_type": str(dr.run_type), "counter": counter,
                                 "prior": prior, "conf": dr.conf}) + "\\n")
        if FAIL_ON == counter:
            raise RuntimeError("planted failure")
        ti.xcom_push(key="mark", value=str(dr.run_after))

    step()


stateful()
'''

STATEFUL_2X = '''
import json
import pendulum
from airflow.decorators import dag, task
from airflow.models import Variable


@dag(schedule="0 4 * * *", start_date=pendulum.datetime(2026, 3, 1, tz="UTC"), catchup=False)
def stateful2():
    @task
    def step():
        counter = int(Variable.get("counter", default_var="0")) + 1
        Variable.set("counter", str(counter))
        with open(OUT, "a") as fh:
            fh.write(json.dumps({"counter": counter}) + "\\n")

    step()


stateful2()
'''

HANGS = '''
import pendulum
from airflow.sdk import dag
from airflow.providers.standard.sensors.python import PythonSensor


@dag(schedule="0 4 * * *", start_date=pendulum.datetime(2026, 3, 1, tz="UTC"), catchup=False)
def hangs():
    PythonSensor(task_id="never", python_callable=lambda: False, poke_interval=1, timeout=3600,
                 mode="poke")


hangs()
'''


def run(tmp_path, key, *args):
    env = clean_environ(AIRFLOW_HOME=str(tmp_path / "home"))
    proc = subprocess.run([env_python(key), str(SCRIPT), *args], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=900)
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    return lines, proc


def project(tmp_path, body, fail_on=0):
    dags = tmp_path / "dags"
    dags.mkdir()
    out = tmp_path / "seen.jsonl"
    (dags / "probe.py").write_text(f"OUT = {str(out)!r}\nFAIL_ON = {fail_on}\n" + body)
    return out


def seen(out):
    return [json.loads(line) for line in out.read_text().splitlines()]


def test_scheduled_manual_and_rerun_share_one_db(tmp_path):
    out = project(tmp_path, STATEFUL_3X)
    lines, proc = run(tmp_path, "3.3", "stateful", "--from", "2026-03-02", "--runs", "3",
                      "--manual", "2026-03-03T09:30:00Z", "--rerun", "1", "--var", "counter=10",
                      "--conf", '{"k": 1}', "--show-xcom")
    assert proc.returncode == 0, (lines, proc.stderr[-3000:])
    runs, summary = lines[:-1], lines[-1]["summary"]
    assert summary["runs"] == 5 and summary["failed_runs"] == [] and summary["exit_code"] == 0
    assert [r["kind"] for r in runs] == ["scheduled", "manual", "scheduled", "scheduled", "rerun"]
    first = runs[0]
    # the scheduler's run for an interval timetable, not dag.test()'s inferred manual interval
    assert first["run_type"] == "scheduled"
    assert first["logical_date"].startswith("2026-03-02T04:00")
    assert first["data_interval_start"].startswith("2026-03-02T04:00")
    assert first["data_interval_end"].startswith("2026-03-03T04:00")
    assert runs[1]["logical_date"] is None and runs[1]["run_type"] == "manual"
    assert runs[4]["rerun_of"] == 1 and runs[4]["logical_date"] == first["logical_date"]
    assert "step.mark" in first["xcom"]
    states = seen(out)
    # the seeded Variable is updated run after run: one DB for every run
    assert [s["counter"] for s in states] == [11, 12, 13, 14, 15]
    assert states[0]["prior"] is None and states[1]["prior"] is not None
    assert all(s["conf"] == {"k": 1} for s in states)


def test_failed_run_is_reported_and_later_runs_still_execute(tmp_path):
    project(tmp_path, STATEFUL_3X, fail_on=2)
    lines, proc = run(tmp_path, "3.3", "stateful", "--from", "2026-03-02", "--runs", "3")
    assert proc.returncode == 2, (lines, proc.stderr[-3000:])
    runs, summary = lines[:-1], lines[-1]["summary"]
    assert [r["state"] for r in runs] == ["success", "failed", "success"]
    assert runs[1]["failed_tasks"] == ["step"]
    assert summary["failed_runs"] == [2]


def test_hung_run_times_out_and_stops(tmp_path):
    project(tmp_path, HANGS)
    lines, proc = run(tmp_path, "3.3", "hangs", "--from", "2026-03-02", "--runs", "2",
                      "--run-timeout", "8")
    assert proc.returncode == 2, (lines, proc.stderr[-3000:])
    runs, summary = lines[:-1], lines[-1]["summary"]
    assert len(runs) == 1 and runs[0]["state"] == "timeout"
    assert any("stopped after a hung run" in e for e in summary["errors"])


def test_airflow2_scheduled_runs_and_rerun(tmp_path):
    out = project(tmp_path, STATEFUL_2X)
    lines, proc = run(tmp_path, "2.11", "stateful2", "--from", "2026-03-02", "--runs", "2",
                      "--rerun", "1")
    assert proc.returncode == 0, (lines, proc.stderr[-3000:])
    runs = lines[:-1]
    assert [r["run_type"] for r in runs] == ["scheduled"] * 3
    assert runs[0]["run_id"] == runs[2]["run_id"]
    assert [s["counter"] for s in seen(out)] == [1, 2, 3]


@pytest.mark.parametrize("args,needle", [
    (["no_such_dag"], "not found"),
    (["stateful", "--runs", "2", "--rerun", "3"], "only 2 scheduled runs"),
    (["stateful", "--var", "novalue"], "KEY=VALUE"),
])
def test_usage_errors_exit_3(tmp_path, args, needle):
    project(tmp_path, STATEFUL_3X)
    lines, proc = run(tmp_path, "3.3", *args)
    assert proc.returncode == 3, (lines, proc.stderr[-2000:])
    assert any(needle in e for e in lines[-1]["summary"]["errors"])


def _dag_runs(summary, dag_id):
    import sqlite3

    with sqlite3.connect(summary["metadata_db"]) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(dag_run)")}
        extra = ", external_trigger" if "external_trigger" in cols else ""
        return con.execute(f"SELECT run_type{extra} FROM dag_run WHERE dag_id = ? ORDER BY id",
                           (dag_id,)).fetchall()


def test_successive_manual_runs_keep_earlier_manual_runs(tmp_path):
    project(tmp_path, STATEFUL_3X)
    lines, proc = run(tmp_path, "3.3", "stateful", "--runs", "0",
                      "--manual", "2026-03-03T09:30:00Z", "--manual", "2026-03-04T09:30:00Z")
    assert proc.returncode == 0, (lines, proc.stderr[-3000:])
    summary = lines[-1]["summary"]
    # dag.test() deletes the earlier run with the same (NULL) logical date; the replay must not
    assert [row[0] for row in _dag_runs(summary, "stateful")] == ["manual", "manual"]


def test_airflow2_manual_run_is_external_trigger(tmp_path):
    project(tmp_path, STATEFUL_2X)
    lines, proc = run(tmp_path, "2.11", "stateful2", "--from", "2026-03-02", "--runs", "1",
                      "--manual", "2026-03-03T09:30:00Z")
    assert proc.returncode == 0, (lines, proc.stderr[-3000:])
    rows = _dag_runs(lines[-1]["summary"], "stateful2")
    assert sorted(rows) == [("manual", 1), ("scheduled", 0)]


def test_empty_plan_is_a_usage_error(tmp_path):
    project(tmp_path, STATEFUL_3X)
    lines, proc = run(tmp_path, "3.3", "stateful", "--runs", "0")
    assert proc.returncode == 3, (lines, proc.stderr[-2000:])
    assert any("nothing to run" in e for e in lines[-1]["summary"]["errors"])
