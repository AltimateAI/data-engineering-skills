"""Integration tests: grading helpers against the real Airflow eval envs.

Skipped when an env is missing (create them with evals/harness/setup_envs.sh).
Each version takes roughly 20-40 s.
"""

import textwrap
from pathlib import Path

import grading as g
import pytest

DAGS = {
    "3.3": """
        from datetime import datetime
        from pathlib import Path
        from airflow.sdk import dag, task
        from airflow.operators.bash import BashOperator  # deprecated on 3.x

        OUT = Path(__file__).resolve().parents[1] / "out.txt"

        @dag(schedule="0 3 * * *", start_date=datetime(2026, 1, 1), catchup=False, tags=["t"])
        def good():
            @task
            def write(ds=None):
                with OUT.open("a") as fh:
                    fh.write(ds + "\\n")
            echo = BashOperator(task_id="echo", bash_command="echo hi")
            write() >> echo
        good()

        @dag(schedule=None, start_date=datetime(2026, 1, 1))
        def bad():
            @task
            def boom():
                raise ValueError("boom")
            boom()
        bad()
    """,
    "2.11": """
        from datetime import datetime
        from pathlib import Path
        from airflow.decorators import dag, task
        from airflow.operators.bash import BashOperator

        OUT = Path(__file__).resolve().parents[1] / "out.txt"

        @dag(schedule="0 3 * * *", start_date=datetime(2026, 1, 1), catchup=False, tags=["t"])
        def good():
            @task
            def write(ds=None):
                with OUT.open("a") as fh:
                    fh.write(ds + "\\n")
            echo = BashOperator(task_id="echo", bash_command="echo hi")
            write() >> echo
        good()

        @dag(schedule=None, start_date=datetime(2026, 1, 1))
        def bad():
            @task
            def boom():
                raise ValueError("boom")
            boom()
        bad()
    """,
}

LIB = "def add(a, b):\n    return a + b\n"
BUGGY_LIB = "def add(a, b):\n    return a - b\n"
TESTS = "from lib import add\n\ndef test_add():\n    assert add(2, 2) == 4\n"


def _env_or_skip(version):
    py = g.env_python(version)
    if not Path(py).exists():
        pytest.skip(f"Airflow env {version} missing; run evals/harness/setup_envs.sh")
    return py


@pytest.fixture(params=["3.3", "2.11"])
def af(request, tmp_path):
    py = _env_or_skip(request.param)
    ws = tmp_path / "ws"
    (ws / "dags").mkdir(parents=True)
    (ws / "dags" / "dags.py").write_text(textwrap.dedent(DAGS[request.param]))
    (ws / "dags" / "broken.py").write_text("import nonexistent_module_xyz  # airflow dag\n")
    return request.param, py, ws


def test_import_dags(af):
    version, py, ws = af
    imp = g.import_dags(py, ws)
    assert imp["ok"], imp["probe_error"]
    assert imp["airflow_version"].startswith(version)
    assert set(imp["dags"]) == {"good", "bad"}
    good = imp["dags"]["good"]
    assert good["tasks"] == ["echo", "write"] and good["deps"] == [["write", "echo"]]
    assert good["catchup"] is False and good["tags"] == ["t"]
    expected_tt = "CronTriggerTimetable" if version == "3.3" else "CronDataIntervalTimetable"
    assert good["timetable"] == expected_tt
    assert list(imp["import_errors"]) == ["dags/broken.py"]
    deps = g.deprecation_warnings(imp)
    if version == "3.3":
        assert any("BashOperator" in w["message"] for w in deps)


def test_run_dags_test_success_failure_and_rerun(af):
    version, py, ws = af
    env = g.airflow_env(ws, env_py=py)
    first = g.run_dags_test(py, ws, "good", "2026-03-01", env=env)
    assert first.ok, first.log[-2000:]
    assert first.runs and first.runs[0]["tasks"]["write"] == "success"
    again = g.run_dags_test(py, ws, "good", "2026-03-01", env=env)
    assert again.ok
    assert (ws / "out.txt").read_text().splitlines() == ["2026-03-01", "2026-03-01"]  # really re-executed
    bad = g.run_dags_test(py, ws, "bad", env=env)
    assert not bad.ok and bad.failed_tasks() == ["boom"]


def test_probe_json_timetable(af):
    version, py, ws = af
    res, proc = g.probe_json(py, """
        dag = get_dag("good")  # helpers from grading.PROBE_PRELUDE
        RESULT = {"runs": scheduled_intervals(dag, "2026-01-01T00:00:00+00:00", n=2),
                  "manual": manual_interval(dag, "2026-03-01T05:00:00+00:00")}
    """, ws)
    assert res is not None, proc.tail(30)
    first, second = res["runs"]
    if version == "3.3":  # CronTriggerTimetable: zero-width interval at the tick
        assert first == {"start": "2026-01-01T03:00:00+00:00", "end": "2026-01-01T03:00:00+00:00",
                         "run_after": "2026-01-01T03:00:00+00:00"}
        assert second["start"] == "2026-01-02T03:00:00+00:00"
        assert res["manual"]["start"] == res["manual"]["end"]
    else:  # CronDataIntervalTimetable: previous tick -> this tick, run created at interval end
        assert first == {"start": "2026-01-01T03:00:00+00:00", "end": "2026-01-02T03:00:00+00:00",
                         "run_after": "2026-01-02T03:00:00+00:00"}
        assert res["manual"] == {"start": "2026-02-28T03:00:00+00:00", "end": "2026-03-01T03:00:00+00:00"}


def test_ruff_air(af):
    version, py, ws = af
    codes = {f["code"] for f in g.ruff_air(py, ws)}
    assert "AIR312" in codes  # airflow.operators.bash on both
    neutral = g.ruff_air(py, ws, select=g.air_select_for(version))
    if version == "2.11":
        assert not any(f["code"].startswith("AIR3") for f in neutral)


def test_run_pytest_planted_bug(af):
    version, py, ws = af
    (ws / "lib.py").write_text(LIB)
    (ws / "tests").mkdir()
    (ws / "tests" / "test_lib.py").write_text(TESTS)
    ok = g.run_pytest(py, ws, ["tests"])
    assert ok.status == "passed" and ok.passed == 1, ok.output_tail
    buggy = g.copy_workspace(ws)
    (buggy / "lib.py").write_text(BUGGY_LIB)
    caught = g.run_pytest(py, buggy, ["tests"])
    assert caught.status == "failed" and caught.caught_bug, caught.output_tail
    (buggy / "lib.py").unlink()
    broken = g.run_pytest(py, buggy, ["tests"])
    assert broken.status == "collection_error" and not broken.caught_bug
