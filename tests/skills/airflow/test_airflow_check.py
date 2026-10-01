"""Tests for skills/airflow/_shared/airflow_check.py.

Every test runs the checker as a subprocess with the interpreter of a pinned
Airflow env (``evals/harness/setup_envs.sh``):

    ${EVAL_ENV_ROOT:-~/.cache/des-evals}/airflow-3.3   apache-airflow 3.3.x
    ${EVAL_ENV_ROOT:-~/.cache/des-evals}/airflow-2.11  apache-airflow 2.11.x

Tests for an env that is not installed are skipped.

Static-rule fixtures (``fixtures/static``) declare their expectations inline:
    ``# targets: 3.3 2.11``       envs/target versions the file is checked under
    ``# expect: <rule>``          this line must produce <rule>; no other line may
    ``# near-miss: <rule>, ...``  <rule> must not fire anywhere in the file
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
CHECKER = REPO / "skills" / "airflow" / "_shared" / "airflow_check.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
STATIC = FIXTURES / "static"
ENV_ROOT = Path(os.environ.get("EVAL_ENV_ROOT", "~/.cache/des-evals")).expanduser()
ENVS = {"3.3": ENV_ROOT / "airflow-3.3" / "bin" / "python",
        "2.11": ENV_ROOT / "airflow-2.11" / "bin" / "python"}
SCRUB_PREFIXES = ("AIRFLOW__", "AIRFLOW_CONN_", "AIRFLOW_VAR_")
SCRUB_EXACT = ("AIRFLOW_HOME", "AIRFLOW_CONFIG", "VIRTUAL_ENV", "PYTHONHOME")


def env_python(key: str) -> str:
    py = ENVS[key]
    if not py.exists():
        pytest.skip(f"Airflow {key} env not installed at {py} (run evals/harness/setup_envs.sh)")
    return str(py)


def clean_environ(**extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(SCRUB_PREFIXES) and k not in SCRUB_EXACT}
    env.update({"OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES", "no_proxy": "*",
                "NO_PROXY": "*", "PYTHONDONTWRITEBYTECODE": "1"})
    env.update(extra)
    return env


def run_checker(key: str, *args: str, cwd: Path = FIXTURES, env: dict | None = None,
                python: list[str] | None = None) -> tuple[dict | None, subprocess.CompletedProcess]:
    cmd = python or [env_python(key)]
    proc = subprocess.run([*cmd, str(CHECKER), *args, "--json"], cwd=cwd, env=env or clean_environ(),
                          capture_output=True, text=True, timeout=300)
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        data = None
    return data, proc


def by_id(result: dict) -> dict:
    return {d["dag_id"]: d for d in result["dags"]}


# ---------------------------------------------------------------------------
# Interval preview: the same schedule means different runs on 2.x and 3.x
# ---------------------------------------------------------------------------

EXPECTED_PREVIEW = {
    # schedule="0 6 * * *": 3.x -> CronTriggerTimetable (zero-width interval at the tick);
    # 2.x -> CronDataIntervalTimetable (previous day, run after the interval ends).
    ("3.3", "sched_cron_string"): ("CronTriggerTimetable", [
        ("2026-03-06T06:00:00+00:00", "2026-03-06T06:00:00+00:00",
         "2026-03-06T06:00:00+00:00", "2026-03-06T06:00:00+00:00"),
        ("2026-03-07T06:00:00+00:00", "2026-03-07T06:00:00+00:00",
         "2026-03-07T06:00:00+00:00", "2026-03-07T06:00:00+00:00"),
    ]),
    ("2.11", "sched_cron_string"): ("CronDataIntervalTimetable", [
        ("2026-03-07T06:00:00+00:00", "2026-03-06T06:00:00+00:00",
         "2026-03-06T06:00:00+00:00", "2026-03-07T06:00:00+00:00"),
        ("2026-03-08T06:00:00+00:00", "2026-03-07T06:00:00+00:00",
         "2026-03-07T06:00:00+00:00", "2026-03-08T06:00:00+00:00"),
    ]),
    # Explicit CronDataIntervalTimetable behaves the same on both versions.
    ("3.3", "sched_cron_interval"): ("CronDataIntervalTimetable", [
        ("2026-03-07T06:00:00+00:00", "2026-03-06T06:00:00+00:00",
         "2026-03-06T06:00:00+00:00", "2026-03-07T06:00:00+00:00"),
        ("2026-03-08T06:00:00+00:00", "2026-03-07T06:00:00+00:00",
         "2026-03-07T06:00:00+00:00", "2026-03-08T06:00:00+00:00"),
    ]),
    ("2.11", "sched_cron_interval"): ("CronDataIntervalTimetable", [
        ("2026-03-07T06:00:00+00:00", "2026-03-06T06:00:00+00:00",
         "2026-03-06T06:00:00+00:00", "2026-03-07T06:00:00+00:00"),
        ("2026-03-08T06:00:00+00:00", "2026-03-07T06:00:00+00:00",
         "2026-03-07T06:00:00+00:00", "2026-03-08T06:00:00+00:00"),
    ]),
    # timedelta(days=1): 3.x -> DeltaTriggerTimetable; 2.x -> DeltaDataIntervalTimetable.
    ("3.3", "sched_timedelta"): ("DeltaTriggerTimetable", [
        ("2026-03-06T00:00:00+00:00", "2026-03-06T00:00:00+00:00",
         "2026-03-06T00:00:00+00:00", "2026-03-06T00:00:00+00:00"),
        ("2026-03-07T00:00:00+00:00", "2026-03-07T00:00:00+00:00",
         "2026-03-07T00:00:00+00:00", "2026-03-07T00:00:00+00:00"),
    ]),
    ("2.11", "sched_timedelta"): ("DeltaDataIntervalTimetable", [
        ("2026-03-07T00:00:00+00:00", "2026-03-06T00:00:00+00:00",
         "2026-03-06T00:00:00+00:00", "2026-03-07T00:00:00+00:00"),
        ("2026-03-08T00:00:00+00:00", "2026-03-07T00:00:00+00:00",
         "2026-03-07T00:00:00+00:00", "2026-03-08T00:00:00+00:00"),
    ]),
}


@pytest.fixture(scope="module", params=["3.3", "2.11"])
def schedules(request):
    key = request.param
    data, proc = run_checker(key, "schedules", "--from", "2026-03-06", "--runs", "2")
    assert data is not None, proc.stderr[-3000:]
    return key, data, proc


@pytest.mark.parametrize("dag_id", ["sched_cron_string", "sched_cron_interval", "sched_timedelta"])
def test_interval_preview(schedules, dag_id):
    key, data, proc = schedules
    assert proc.returncode == 0, proc.stdout[-2000:]
    assert data["airflow_version"].startswith(key)
    dag = by_id(data)[dag_id]
    timetable, runs = EXPECTED_PREVIEW[(key, dag_id)]
    assert dag["timetable"] == timetable
    got = [(r["run_after"], r["logical_date"], r["data_interval_start"], r["data_interval_end"])
           for r in dag["next_runs"]]
    assert got == runs


def test_timezone_trigger_crosses_dst(schedules):
    """Weekday 10:00 America/New_York: Friday then Monday, UTC offset changes at DST."""
    _, data, _ = schedules
    runs = by_id(data)["sched_ny_weekdays"]["next_runs"]
    assert [r["run_after"] for r in runs] == ["2026-03-06T15:00:00+00:00",
                                               "2026-03-09T14:00:00+00:00"]
    assert all(r["data_interval_start"] == r["data_interval_end"] for r in runs)


def test_dag_metadata_and_warnings(schedules):
    key, data, _ = schedules
    dags = by_id(data)
    manual = dags["sched_manual_only"]
    assert manual["timetable"] == "NullTimetable" and manual["next_runs"] == []
    assert manual["schedule"] is None
    cron = dags["sched_cron_string"]
    assert cron["catchup"] is False
    assert cron["start_date"] == "2026-01-01T00:00:00+00:00"
    assert cron["tasks"] == 1 and cron["max_active_runs"] == 16
    assert cron["file"] == "schedules/intervals.py"
    trigger_warned = any("CronTriggerTimetable" in w for w in cron["warnings"])
    assert trigger_warned is (key == "3.3")
    assert any("CronTriggerTimetable" in w for w in dags["sched_ny_weekdays"]["warnings"])
    assert not any("TriggerTimetable" in w for w in dags["sched_cron_interval"]["warnings"])
    hourly = dags["sched_catchup_hourly"]
    assert any(w.startswith("catchup=True: about 1000+ runs") for w in hourly["warnings"])


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_trigger_timetable_with_interval_is_not_warned(key, tmp_path):
    """CronTriggerTimetable(interval=...) carries a real period, so no zero-width warning."""
    imp = ("from airflow.sdk import DAG, CronTriggerTimetable" if key == "3.3" else
           "from airflow import DAG\nfrom airflow.timetables.trigger import CronTriggerTimetable")
    (tmp_path / "tt.py").write_text(
        f"from datetime import timedelta\nimport pendulum\n{imp}\n"
        "with DAG('tt_interval', start_date=pendulum.datetime(2026, 1, 1, tz='UTC'), catchup=False,\n"
        "         schedule=CronTriggerTimetable('0 4 * * *', timezone='UTC',\n"
        "                                       interval=timedelta(days=1))):\n    pass\n")
    data, proc = run_checker(key, "tt.py", "--runs", "2", cwd=tmp_path)
    assert data is not None, proc.stderr[-2000:]
    dag = by_id(data)["tt_interval"]
    assert all(r["data_interval_start"] != r["data_interval_end"] for r in dag["next_runs"])
    assert not any("TriggerTimetable" in w for w in dag["warnings"])


def test_preview_defaults_to_start_date(schedules):
    key = schedules[0]
    data, proc = run_checker(key, "schedules", "--dag-id", "sched_cron_interval", "--runs", "1")
    assert proc.returncode == 0
    (dag,) = data["dags"]
    assert dag["next_runs"][0]["data_interval_start"] == "2026-01-01T06:00:00+00:00"
    assert dag["preview_from"] == "2026-01-01T00:00:00+00:00"


def test_from_before_start_date_is_clamped(schedules):
    key = schedules[0]
    data, _ = run_checker(key, "schedules", "--dag-id", "sched_timedelta", "--runs", "1",
                          "--from", "2025-06-01")
    assert data["dags"][0]["next_runs"][0]["data_interval_start"] == "2026-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Exit codes, import errors, output contract, isolation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_clean_project_exits_zero(key):
    data, proc = run_checker(key, "clean")
    assert proc.returncode == 0, proc.stdout
    assert data["exit_code"] == 0
    assert data["import_errors"] == []
    assert [f for f in data["findings"] if f["severity"] == "error"] == []
    assert by_id(data)["clean_daily"]["tasks"] == 2


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_import_errors_exit_one(key):
    data, proc = run_checker(key, "import_error")
    assert proc.returncode == 1
    (err,) = data["import_errors"]
    assert err["file"] == "import_error/broken_dag.py"
    assert "module_that_does_not_exist_anywhere" in err["error"]
    assert len(err["error"]) <= 1600 and len(err["error"].splitlines()) <= 20
    assert "still_good" in by_id(data)  # other files still load


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_findings_only_exit_two_and_runtime_sensor_warning(key):
    data, proc = run_checker(key, "findings_only")
    assert proc.returncode == 2, proc.stdout
    assert data["import_errors"] == []
    assert [f["rule"] for f in data["findings"] if f["severity"] == "error"] == [
        "sensor-poke-no-timeout"]
    dag = by_id(data)["waits_for_file"]
    assert any(w.startswith("sensor wait_for_drop pokes") for w in dag["warnings"])


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_warnings_do_not_fail(key):
    data, proc = run_checker(key, "--static-only", "static/wall_clock_pos.py")
    assert data["summary"]["findings_warning"] >= 5
    assert data["summary"]["findings_error"] == 0
    assert proc.returncode == 0


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_usage_errors_exit_three(key):
    data, proc = run_checker(key, "does/not/exist")
    assert proc.returncode == 3 and "path not found" in data["errors"][0]
    _, proc = run_checker(key, "clean", "--runs", "500")
    assert proc.returncode == 3
    _, proc = run_checker(key, "clean", "--from", "yesterday")
    assert proc.returncode == 3
    data, proc = run_checker(key, "clean", "--dag-id", "no_such_dag")
    assert proc.returncode == 3 and data["errors"] == ["dag_id not found: no_such_dag"]


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_dag_id_filters_dags_and_findings(key):
    data, proc = run_checker(key, "clean", "findings_only", "--dag-id", "clean_daily")
    assert [d["dag_id"] for d in data["dags"]] == ["clean_daily"]
    assert data["findings"] == [] or all(f["file"] == "clean/clean_dag.py" for f in data["findings"])
    assert proc.returncode == 0


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_stdout_is_pure_json_despite_airflow_logging(key):
    py = env_python(key)
    proc = subprocess.run([py, str(CHECKER), "schedules", "import_error", "--json"], cwd=FIXTURES,
                          env=clean_environ(AIRFLOW__LOGGING__LOGGING_LEVEL="INFO"),
                          capture_output=True, text=True, timeout=300)
    data = json.loads(proc.stdout)  # raises if any log line leaked into stdout
    assert data["exit_code"] == proc.returncode == 1


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_text_output(key):
    py = env_python(key)
    proc = subprocess.run([py, str(CHECKER), "findings_only"], cwd=FIXTURES, env=clean_environ(),
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 2
    assert "DAG waits_for_file" in proc.stdout
    assert "sensor-poke-no-timeout" in proc.stdout
    assert proc.stdout.rstrip().endswith("exit 2")


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_never_touches_configured_metadata_db(key, tmp_path):
    """A configured AIRFLOW_HOME/DB is left alone; parse-time lookups hit a throwaway DB."""
    home = tmp_path / "home"
    home.mkdir()
    real_db = tmp_path / "real.db"
    env = clean_environ(AIRFLOW_HOME=str(home),
                        AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=f"sqlite:///{real_db}")
    data, proc = run_checker(key, "env_isolation", env=env)
    assert data is not None, proc.stderr[-2000:]
    assert not real_db.exists()
    assert not (home / "airflow.db").exists()
    assert any(f["rule"] == "top-level-io" for f in data["findings"])
    assert proc.returncode in (1, 2)


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_default_path_uses_dags_folder(key, tmp_path):
    dags = tmp_path / "dags"
    dags.mkdir()
    (dags / "d.py").write_text((FIXTURES / "clean" / "clean_dag.py").read_text())
    data, proc = run_checker(key, cwd=tmp_path)
    assert proc.returncode == 0, proc.stdout
    assert [d["dag_id"] for d in data["dags"]] == ["clean_daily"]


def test_missing_airflow_is_env_error(tmp_path):
    """Plain python without Airflow: exit 3, unless --static-only with --target-version."""
    no_site = [sys.executable, "-S"]  # stdlib only: Airflow is not importable
    probe = subprocess.run([*no_site, "-c", "import airflow"], capture_output=True)
    if probe.returncode == 0:
        pytest.skip("Airflow importable without site-packages")
    data, proc = run_checker("", "clean", python=no_site)
    assert proc.returncode == 3 and data["errors"]
    data, proc = run_checker("", "--static-only", "--target-version", "3.3",
                             "static/sla_pos.py", python=no_site)
    assert proc.returncode == 2
    assert {f["rule"] for f in data["findings"]} >= {"sla-ignored"}


# ---------------------------------------------------------------------------
# Static rules: inline expectations in fixtures/static
# ---------------------------------------------------------------------------

EXPECT_RE = re.compile(r"#\s*expect:\s*([\w-]+(?:\s*,\s*[\w-]+)*)")
NEAR_MISS_RE = re.compile(r"#\s*near-miss:\s*([\w-]+(?:\s*,\s*[\w-]+)*)")
TARGETS_RE = re.compile(r"#\s*targets:\s*([\d.\s]+)")


def static_cases():
    cases = []
    for path in sorted(STATIC.glob("*.py")):
        text = path.read_text()
        targets = TARGETS_RE.search(text).group(1).split()
        for key in targets:
            cases.append(pytest.param(key, path.name, id=f"{path.stem}-{key}"))
    return cases


def parse_expectations(text: str):
    expected: dict[str, set[int]] = {}
    near: set[str] = set()
    for i, line in enumerate(text.splitlines(), start=1):
        m = EXPECT_RE.search(line)
        if m:
            for rule in re.split(r"\s*,\s*", m.group(1)):
                expected.setdefault(rule, set()).add(i)
        m = NEAR_MISS_RE.search(line)
        if m:
            near.update(re.split(r"\s*,\s*", m.group(1)))
    return expected, near


@pytest.mark.parametrize("key,name", static_cases())
def test_static_rule_fixture(key, name):
    text = (STATIC / name).read_text()
    expected, near = parse_expectations(text)
    assert expected or near, f"{name} declares no expectations"
    data, proc = run_checker(key, "--static-only", "--target-version", key, f"static/{name}")
    assert data is not None, proc.stderr[-2000:]
    got: dict[str, set[int]] = {}
    for f in data["findings"]:
        got.setdefault(f["rule"], set()).add(f["line"])
    for rule, lines in expected.items():
        assert got.get(rule, set()) == lines, (rule, data["findings"])
    for rule in near:
        assert rule not in got, (rule, [f for f in data["findings"] if f["rule"] == rule])


def test_every_rule_has_positive_and_near_miss_fixture():
    positives, negatives = set(), set()
    for path in STATIC.glob("*.py"):
        expected, near = parse_expectations(path.read_text())
        positives |= set(expected)
        negatives |= near
    rules = {"removed-context-key", "xcom-pull-no-task-ids", "top-level-io", "dynamic-dag-arg",
             "sensor-poke-no-timeout", "sdk-import-on-2x", "removed-dag-kwarg", "removed-kwarg",
             "sla-ignored", "db-access-in-task", "wall-clock-in-task", "reserved-context-param",
             "manual-run-dates", "schedule-missing", "catchup-implicit"}
    assert rules <= positives, rules - positives
    assert rules <= negatives, rules - negatives


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_static_rule_severity_depends_on_target(key):
    data, _ = run_checker(key, "--static-only", "--target-version", key, "static/xcom_pull_pos.py")
    sev = {f["severity"] for f in data["findings"] if f["rule"] == "xcom-pull-no-task-ids"}
    # Jinja xcom_pull() is only reported for 3.x; the Python calls are errors on 3.x, warnings on 2.x.
    assert sev == ({"error"} if key == "3.3" else {"warning"})


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_template_files_are_scanned(key):
    data, proc = run_checker(key, "--static-only", "--target-version", key, "static/templates")
    hits = [(f["file"], f["line"]) for f in data["findings"] if f["rule"] == "removed-context-key"]
    if key == "3.3":
        assert hits == [("static/templates/removed_key.sql", 3)]
        assert proc.returncode == 2
    else:
        assert hits == [] and proc.returncode == 0


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_installed_version_is_default_target(key):
    data, _ = run_checker(key, "--static-only", "static/sdk_import_pos.py")
    rules = {f["rule"] for f in data["findings"]}
    assert data["target_version"].startswith(key)
    assert ("sdk-import-on-2x" in rules) is (key == "2.11")


def test_findings_are_bounded(tmp_path):
    lines = ["from airflow.models import Variable"] + [
        f"V{i} = Variable.get('k{i}')" for i in range(300)]
    (tmp_path / "many.py").write_text("\n".join(lines) + "\n")
    key = "3.3" if ENVS["3.3"].exists() else "2.11"
    data, proc = run_checker(key, "--static-only", "many.py", cwd=tmp_path)
    assert len(data["findings"]) == 200
    assert data["summary"]["findings_truncated"] == 100
    assert data["summary"]["findings_error"] == 300
    assert proc.returncode == 2


# ---------------------------------------------------------------------------
# Vendored copies must stay identical to the canonical script
# ---------------------------------------------------------------------------


def test_vendored_copies_match_canonical():
    canonical = CHECKER.read_bytes()
    copies = sorted((REPO / "skills" / "airflow").glob("*/scripts/airflow_check.py"))
    stale = [str(p.relative_to(REPO)) for p in copies if p.read_bytes() != canonical]
    assert stale == [], f"re-copy skills/airflow/_shared/airflow_check.py into: {stale}"


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_removed_conf_only_context_uses(key, tmp_path):
    source = '''from airflow.decorators import task
from airflow.configuration import conf
@task
def broken(**context):
    return context["conf"], context.get("conf")
bad_template = "{{ conf.get('core', 'dags_folder') }}"
plain = conf.get("core", "dags_folder")
def helper(conf, **kwargs):
    return conf, kwargs["conf"]
other = {"conf": 1}["conf"]
good_template = "{{ params.conf }} {{ dag_run.conf }} {{ 'conf' }}"
@task
def supplied_conf(conf=None):
    return conf
supplied_conf(conf={"user": "value"})
@task
def local_conf():
    conf = {"user": "value"}
    return conf["user"]
'''
    (tmp_path / "conf.py").write_text(source)
    data, proc = run_checker(key, "conf.py", "--static-only", cwd=tmp_path)
    hits = [f for f in data["findings"] if f["rule"] == "removed-context-key"]
    assert {f["line"] for f in hits} == ({5, 6} if key == "3.3" else set())
    assert proc.returncode == (2 if key == "3.3" else 0)


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_missing_optional_plugins_still_scans_dags(key, tmp_path):
    (tmp_path / "dags").mkdir()
    (tmp_path / "dags" / "d.py").write_text((FIXTURES / "clean" / "clean_dag.py").read_text())
    data, proc = run_checker(key, "dags", "plugins", cwd=tmp_path)
    assert proc.returncode == 0, proc.stdout
    assert data["summary"]["files_scanned"] == 1
    assert "clean_daily" in by_id(data)
    _, missing = run_checker(key, "plugins", cwd=tmp_path)
    assert missing.returncode == 3
    _, typo = run_checker(key, "dags", "plguins", cwd=tmp_path)
    assert typo.returncode == 3


def test_dag_id_preserves_template_findings(tmp_path):
    (tmp_path / "dags" / "sql").mkdir(parents=True)
    (tmp_path / "dags" / "sql" / "run.sh").write_text("echo {{ execution_date }}\n")
    (tmp_path / "dags" / "d.py").write_text('''from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator
with DAG("external_template", schedule=None):
    BashOperator(task_id="run", bash_command="sql/run.sh")
''')
    data, proc = run_checker("3.3", "dags", "--dag-id", "external_template", cwd=tmp_path)
    assert proc.returncode == 2, proc.stdout
    assert any(f["file"] == "dags/sql/run.sh" and f["rule"] == "removed-context-key"
               for f in data["findings"])


@pytest.mark.parametrize("key", ["3.3", "2.11"])
@pytest.mark.parametrize("param", ["run_after", "next_ds", "conf", "try_number", "exception",
                                   "expanded_ti_count", "task_reschedule_count"])
def test_reserved_context_params_match_real_imports(key, param, tmp_path):
    (tmp_path / "mapped.py").write_text(f'''from airflow.decorators import task
from airflow import DAG
@task
def consume({param}=None):
    return {param}
with DAG("mapped", schedule=None):
    consume.expand({param}=[1, 2])
''')
    data, proc = run_checker(key, "mapped.py", cwd=tmp_path)
    reserved = param in {"try_number", "exception", "expanded_ti_count"} or (
        key == "3.3" and param == "task_reschedule_count") or (key == "2.11" and param in {"next_ds", "conf"})
    assert bool(data["import_errors"]) is reserved, proc.stdout
    hits = [f for f in data["findings"] if f["rule"] == "reserved-context-param"]
    assert bool(hits) is reserved, proc.stdout
    assert proc.returncode == (1 if reserved else 0), proc.stdout


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_once_and_hybrid_schedules_are_previewed(key, tmp_path):
    imports = ("from airflow.sdk import DAG, Asset\n"
               "from airflow.sdk import AssetOrTimeSchedule\n"
               "condition = {'assets': [Asset('s3://bucket/input')]}\n"
               "Hybrid = AssetOrTimeSchedule\n") if key == "3.3" else (
               "from airflow import DAG, Dataset\n"
               "from airflow.timetables.datasets import DatasetOrTimeSchedule\n"
               "condition = {'datasets': [Dataset('s3://bucket/input')]}\n"
               "Hybrid = DatasetOrTimeSchedule\n")
    (tmp_path / "schedules.py").write_text(imports + '''import pendulum
from airflow.timetables.interval import CronDataIntervalTimetable
start = pendulum.datetime(2026, 1, 1, tz="UTC")
with DAG("once", schedule="@once", start_date=start, catchup=False):
    pass
with DAG("hybrid", schedule=Hybrid(timetable=CronDataIntervalTimetable("0 4 * * *", timezone="UTC"),
                                  **condition), start_date=start, catchup=False):
    pass
''')
    data, proc = run_checker(key, "schedules.py", "--runs", "2", cwd=tmp_path)
    assert proc.returncode == 0, proc.stdout
    assert len(by_id(data)["once"]["next_runs"]) == 1
    hybrid = by_id(data)["hybrid"]
    assert len(hybrid["next_runs"]) == 2
    assert hybrid["next_runs"][0]["data_interval_start"] == "2026-01-01T04:00:00+00:00"
    assert hybrid["next_runs"][0]["data_interval_end"] == "2026-01-02T04:00:00+00:00"


@pytest.mark.parametrize("key", ["3.3", "2.11"])
@pytest.mark.parametrize("source,rule", [
    ('''from airflow import DAG
from datetime import datetime
with DAG("macros", schedule=None, user_defined_macros={"clock": lambda: datetime.now()},
         on_success_callback=lambda context: datetime.now()):
    pass
''', "dynamic-dag-arg"),
    ('''from airflow import DAG
from airflow.sensors.external_task import ExternalTaskSensor
with DAG("sensors", schedule=None, default_args={"deferrable": True}):
    ExternalTaskSensor(task_id="sensor", external_dag_id="upstream")
''', "sensor-poke-no-timeout"),
    ('''from airflow.decorators import task
@task
def one(**kwargs):
    return kwargs["ds"]
def helper(**kwargs):
    return kwargs["prev_ds"]
''', "removed-context-key"),
    ('''from airflow.decorators import dag
from datetime import datetime
@dag(schedule=None)
def build():
    today = datetime.now().date()
build()
''', "wall-clock-in-task"),
])
def test_static_rules_respect_execution_scope(key, source, rule, tmp_path):
    (tmp_path / "scope.py").write_text(source)
    data, proc = run_checker(key, "scope.py", "--static-only", cwd=tmp_path)
    assert not [f for f in data["findings"] if f["rule"] == rule], proc.stdout


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_reserved_context_key_sets_match_installed_airflow(key, tmp_path):
    module = "airflow.sdk.definitions.context" if key == "3.3" else "airflow.utils.context"
    code = f'''import runpy
from {module} import KNOWN_CONTEXT_KEYS
checker = runpy.run_path({str(CHECKER)!r})
assert checker["CONTEXT_KEYS_{key[0]}"] == KNOWN_CONTEXT_KEYS
'''
    proc = subprocess.run([env_python(key), "-c", code], env=clean_environ(AIRFLOW_HOME=str(tmp_path)),
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr


def test_explicit_conf_template_macro_is_not_removed_context(tmp_path):
    (tmp_path / "macros.py").write_text('''from airflow.sdk import DAG, conf
from airflow.providers.standard.operators.bash import BashOperator
with DAG("custom_conf", schedule=None, user_defined_macros={"conf": conf}):
    BashOperator(task_id="custom", bash_command="{{ conf.get('core', 'dags_folder') }}")
with DAG("removed_conf", schedule=None):
    BashOperator(task_id="removed", bash_command="{{ conf.get('core', 'dags_folder') }}")
''')
    data, _ = run_checker("3.3", "macros.py", "--static-only", cwd=tmp_path)
    assert [f["line"] for f in data["findings"] if f["rule"] == "removed-context-key"] == [6]


@pytest.mark.parametrize("key", ["3.3", "2.11"])
def test_lambda_defaults_and_immediate_calls_still_run_at_parse_time(key, tmp_path):
    (tmp_path / "lambdas.py").write_text('''from airflow import DAG
from datetime import datetime
with DAG("macros", schedule=None,
         user_defined_macros={"clock": lambda now=datetime.now(): now},
         start_date=(lambda: datetime.now())()):
    pass
''')
    data, proc = run_checker(key, "lambdas.py", "--static-only", cwd=tmp_path)
    assert [f["line"] for f in data["findings"] if f["rule"] == "dynamic-dag-arg"] == [4, 5]
    assert proc.returncode == 2
