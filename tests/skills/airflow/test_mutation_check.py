"""Tests for skills/airflow/testing-airflow-dags/scripts/mutation_check.py.

The script is Airflow-agnostic (it only runs pytest), so these tests use a tiny
pure-Python project and whatever Python runs this suite.
"""
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[3] / "skills" / "airflow" / "testing-airflow-dags"
          / "scripts" / "mutation_check.py")

MODULE = '''\
def late(promised, delivered, run_date):
    if delivered is None:
        return promised < run_date
    return delivered == run_date and delivered > promised


RETRIES = 2
'''

TESTS = '''\
from calc import late


def test_late_delivered():
    assert late("2026-03-01", "2026-03-03", "2026-03-03")


def test_on_time():
    assert not late("2026-03-03", "2026-03-03", "2026-03-03")


def test_open_overdue():
    assert late("2026-03-01", None, "2026-03-03")
'''


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text(MODULE)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "conftest.py").write_text(
        "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1] / 'src'))\n")
    (tmp_path / "tests" / "test_calc.py").write_text(TESTS)
    return tmp_path


def run(project, *args):
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=project,
                          capture_output=True, text=True, timeout=300)
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        data = None
    return proc.returncode, data, proc


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_caught_survived_and_restored(project):
    src = project / "src" / "calc.py"
    before, mtime = digest(src), src.stat().st_mtime_ns
    code, data, _ = run(project,
                        "--mutation", "src/calc.py", "return promised < run_date", "return False",
                        "--mutation", "src/calc.py", "RETRIES = 2", "RETRIES = 0")
    assert code == 2
    assert data["baseline"]["passed"] == 3
    caught = {m["id"]: m["caught"] for m in data["mutants"]}
    assert caught == {0: True, 1: False}  # nothing tests RETRIES
    assert data["mutants"][0]["caught_by"][0]["test"].endswith("test_open_overdue")
    assert data["summary"]["survived_ids"] == [1]
    assert data["restored"] is True
    assert digest(src) == before and src.stat().st_mtime_ns == mtime


def test_all_caught_exit_0_with_pytest_args(project):
    code, data, _ = run(project, "--mutation", "src/calc.py", "delivered > promised", "delivered >= promised",
                        "--", "tests", "-k", "on_time")
    assert code == 0
    assert data["pytest_args"] == ["tests", "-k", "on_time"]
    assert data["summary"]["caught"] == 1


def test_red_baseline_exit_1(project):
    (project / "tests" / "test_broken.py").write_text("def test_x():\n    assert False\n")
    code, data, _ = run(project, "--mutation", "src/calc.py", "RETRIES = 2", "RETRIES = 0")
    assert code == 1
    assert "mutants" not in data


def test_collection_only_flagged(project, tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([{"file": "src/calc.py", "old": "def late(promised, delivered, run_date):",
                                 "new": "def late(promised, delivered, run_date)", "why": "syntax"}]))
    code, data, _ = run(project, "--spec", str(spec))
    assert code == 0
    assert data["summary"]["caught_only_by_collection_error"] == [0]
    assert "SyntaxError" in data["mutants"][0]["caught_by"][0]["message"]


@pytest.mark.parametrize("args", [
    ["--mutation", "src/calc.py", "not in file", "x"],
    ["--mutation", "src/missing.py", "a", "b"],
    ["--mutation", "src/calc.py", "run_date", "day"],  # occurs more than once
    ["--bogus"],
    [],
])
def test_usage_errors_exit_3(project, args):
    code, _, _ = run(project, *args)
    assert code == 3
    assert digest(project / "src" / "calc.py") == hashlib.sha256(MODULE.encode()).hexdigest()


def test_pytest_crash_is_inconclusive_not_caught(project):
    """A mutation that breaks conftest makes pytest exit 4 with no failing test: not proof."""
    conftest = project / "tests" / "conftest.py"
    code, data, _ = run(project, "--mutation", "tests/conftest.py", "import sys, pathlib",
                        "import sys, pathlib, no_such_module_xyz")
    assert code == 2
    mutant = data["mutants"][0]
    assert mutant["caught"] is False and mutant["inconclusive"] is True
    assert data["summary"]["inconclusive_ids"] == [0] and data["summary"]["survived_ids"] == []
    assert "no_such_module_xyz" not in conftest.read_text()


def test_crlf_file_mutation_is_really_applied(project):
    src = project / "src" / "calc.py"
    src.write_bytes(MODULE.replace("\n", "\r\n").encode())
    code, _, _ = run(project, "--mutation", "src/calc.py",
                     "if delivered is None:\n        return", "if delivered is None:\n        return not")
    assert code == 3  # LF text is not in a CRLF file: refused instead of a silent no-op
    code, data, _ = run(project, "--mutation", "src/calc.py", "promised < run_date",
                        "promised > run_date")
    assert code == 0 and data["mutants"][0]["caught"] is True
    assert b"\r\n" in src.read_bytes()


def interrupt_mutation(project, signum, before_signal=None):
    """Signal the real runner only, once its pytest child has observed the mutation."""
    marker = project / "mutated"
    (project / "tests" / "test_interrupt.py").write_text(
        "import pathlib, time\nfrom calc import RETRIES\n"
        "def test_retries():\n"
        "    marker = pathlib.Path('mutated')\n"
        "    if RETRIES == 0 and not marker.exists():\n"
        "        marker.touch()\n"
        "        time.sleep(300)\n"
        "    assert RETRIES == 2\n"
    )
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--mutation", "src/calc.py", "RETRIES = 2", "RETRIES = 0"],
        cwd=project, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 30
        while not marker.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists(), "mutation did not reach the pytest child"
        if before_signal is not None:
            before_signal()
        proc.send_signal(signum)
        proc.wait(timeout=30)
    finally:
        # SIGKILL cannot let the runner reap pytest; clean its entire session in the test.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate(timeout=30)


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP])
def test_signal_restores_original_bytes_and_mtime(project, signum):
    src = project / "src" / "calc.py"
    original, mtime = src.read_bytes(), src.stat().st_mtime_ns
    interrupt_mutation(project, signum)
    assert src.read_bytes() == original
    assert src.stat().st_mtime_ns == mtime


def test_sigkill_journal_recovers_before_validating_mutations(project):
    src = project / "src" / "calc.py"
    original, mtime = src.read_bytes(), src.stat().st_mtime_ns
    interrupt_mutation(project, signal.SIGKILL)
    assert b"RETRIES = 0" in src.read_bytes()
    code, data, proc = run(project, "--mutation", "src/calc.py", "RETRIES = 2", "RETRIES = 0")
    assert code == 0, proc.stdout + proc.stderr
    assert data["baseline"]["passed"] == 4
    assert src.read_bytes() == original
    assert src.stat().st_mtime_ns == mtime


def test_active_run_does_not_restore_another_mutation(project):
    def retry_while_active():
        code, data, proc = run(project, "--mutation", "src/calc.py", "RETRIES = 2", "RETRIES = 0")
        assert code == 3, proc.stdout + proc.stderr
        assert "another mutation check is active" in data["error"]
        assert b"RETRIES = 0" in (project / "src" / "calc.py").read_bytes()
        assert (project / ".mutation-check.json").exists()

    interrupt_mutation(project, signal.SIGTERM, before_signal=retry_while_active)
    assert (project / "src" / "calc.py").read_text() == MODULE
    assert not (project / ".mutation-check.json").exists()
