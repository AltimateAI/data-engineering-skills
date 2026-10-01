"""Tests for skills/airflow/_shared/manual_run.py (Airflow 3 manual trigger with no logical date)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from test_airflow_check import clean_environ, env_python

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "skills" / "airflow" / "_shared" / "manual_run.py"

DAG = '''
import json
import pendulum
from airflow.sdk import dag, task, get_current_context


@dag(schedule="0 4 * * *", start_date=pendulum.datetime(2026, 1, 1, tz="UTC"), catchup=False)
def manual_probe():
    @task
    def record():
        ctx = get_current_context()
        dr = ctx["dag_run"]
        out = {"logical_date": str(dr.logical_date), "run_after": str(dr.run_after),
               "has_ds": "ds" in ctx, "conf": dr.conf}
        with open(OUT, "w") as fh:
            json.dump(out, fh)

    record()


manual_probe()
'''


def run(tmp_path, *args, extra_env=None):
    env = clean_environ(AIRFLOW_HOME=str(tmp_path / "home"), **(extra_env or {}))
    proc = subprocess.run([env_python("3.3"), str(SCRIPT), *args], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=600)
    return json.loads(proc.stdout), proc


@pytest.fixture
def project(tmp_path):
    dags = tmp_path / "dags"
    dags.mkdir()
    out = tmp_path / "out.json"
    (dags / "manual_probe.py").write_text(f"OUT = {str(out)!r}\n" + DAG)
    return tmp_path, out


def test_manual_run_has_no_logical_date_and_passes_conf(project):
    tmp_path, out = project
    data, proc = run(tmp_path, "manual_probe", "--run-after", "2026-03-10T00:30:00Z",
                     "--conf", '{"day": "2026-03-04"}')
    assert proc.returncode == 0, (data, proc.stderr[-2000:])
    assert data["state"].endswith("success") and data["logical_date"] is None
    seen = json.loads(out.read_text())
    assert seen["logical_date"] == "None" and seen["has_ds"] is False
    assert seen["run_after"].startswith("2026-03-10 00:30:00")
    assert seen["conf"] == {"day": "2026-03-04"}


def test_dags_folder_flag_overrides_environment(project):
    tmp_path, _ = project
    other = tmp_path / "elsewhere"
    other.mkdir()
    data, proc = run(tmp_path, "manual_probe", "--dags-folder", "dags",
                     extra_env={"AIRFLOW__CORE__DAGS_FOLDER": str(other)})
    assert proc.returncode == 0, (data, proc.stderr[-2000:])


def test_usage_errors_exit_3(project):
    tmp_path, _ = project
    data, proc = run(tmp_path, "no_such_dag")
    assert proc.returncode == 3 and "not found" in data["errors"][0]
    data, proc = run(tmp_path, "manual_probe", "--conf", "[1]")
    assert proc.returncode == 3


def test_airflow_2_is_usage_error(project):
    tmp_path, _ = project
    env = clean_environ(AIRFLOW_HOME=str(tmp_path / "home2"))
    proc = subprocess.run([env_python("2.11"), str(SCRIPT), "manual_probe"], cwd=tmp_path,
                          env=env, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 3 and "Airflow < 3.0" in json.loads(proc.stdout)["errors"][0]
