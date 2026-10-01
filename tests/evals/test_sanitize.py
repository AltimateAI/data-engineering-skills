"""Tests for evals/harness/sanitize.py, including a scan of committed eval results."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import sanitize as san

REPO = Path(__file__).resolve().parents[2]


def roots(tmp_path):
    return ((str(tmp_path / "home/me/repo"), "<repo>"), (str(tmp_path / "home/me/.cache/des-evals/work"), "<work>"),
            ("/private/var/folders/ab/xyz/T", "<tmp>"), (str(tmp_path / "home/me"), "~"))


def test_sanitize_text_replacements(tmp_path):
    h = tmp_path / "home/me"
    text = (f"{h}/repo/evals/x.py {h}/.cache/des-evals/work/run/ws {h}/.local/share/a "
            f"/private/var/folders/ab/xyz/T/eval-1 /tmp/x /private/tmp/claude/y {h}/repository")
    out = san.sanitize_text(text, roots(tmp_path))
    assert out == ("<repo>/evals/x.py <work>/run/ws ~/.local/share/a <tmp>/eval-1 <tmp>/x <tmp>/claude/y "
                   "~/repository")


def test_sanitize_generic_patterns():
    text = "/Users/someone/x /home/ci/y /var/folders/zz/abc/T/q /usr/bin/python ./rel/tmp/x"
    out = san.sanitize_text(text, ())
    assert out == "~/x ~/y <tmp>/q /usr/bin/python ./rel/tmp/x"
    assert not san.LEAK_PATTERN.search(out)
    for leak in ("/tmp/x", "/private/tmp/x", "/var/folders/ab/c/T/x", "/Users/me/x", "/home/me/x"):
        assert san.LEAK_PATTERN.search(leak), leak
    # bare or truncated /var/folders references (an agent's `ls /var/folders/`)
    out = san.sanitize_text('"path": "/var/folders/" /private/var/folders/gf/abc', ())
    assert out == '"path": "<tmp>/" <tmp>/gf/abc' and not san.LEAK_PATTERN.search(out)


def test_default_roots_cover_repo_home_and_work():
    labels = {label for _, label in san.default_roots()}
    assert labels == {"<repo>", "<work>", "<tmp>", "~"}
    assert san.sanitize_text(str(san.REPO_ROOT / "evals")) == "<repo>/evals"
    work_root = Path(os.environ.get("EVAL_WORK_ROOT", "~/.cache/des-evals/work")).expanduser().resolve()
    assert san.sanitize_text(str(work_root / "x")) == "<work>/x"
    assert san.sanitize_text(os.path.expanduser("~/.cache/des-evals/agent-airflow-3.3")) == \
        "~/.cache/des-evals/agent-airflow-3.3"


def test_writers_and_obj(tmp_path):
    obj = {"path": str(san.REPO_ROOT / "a"), "nested": [os.path.expanduser("~/x"), 3], "n": None}
    assert san.sanitize_obj(obj) == {"path": "<repo>/a", "nested": ["~/x", 3], "n": None}
    san.write_json(tmp_path / "a.json", obj)
    assert json.loads((tmp_path / "a.json").read_text())["path"] == "<repo>/a"
    san.append_jsonl(tmp_path / "r.jsonl", obj)
    san.append_jsonl(tmp_path / "r.jsonl", obj)
    assert len((tmp_path / "r.jsonl").read_text().splitlines()) == 2


def test_sanitize_file_drops_binary_hunks_and_airflow_secrets(tmp_path):
    p = tmp_path / "agent.patch"
    p.write_text(f"+path = '{os.path.expanduser('~/x')}'\n")
    assert san.sanitize_file(p) and "'~/x'" in p.read_text()
    home = os.path.expanduser("~/x")
    b = tmp_path / "bin.patch"
    b.write_text(f"diff --git a/x.db b/x.db\nGIT binary patch\nliteral 10\n{home}\n\ndiff --git a/y.py b/y.py\n+y = 1\n")
    assert san.sanitize_file(b)
    out = b.read_text()
    assert home not in out and "GIT binary patch" not in out and "+y = 1" in out
    c = tmp_path / "cfg.patch"
    c.write_text("+fernet_key = abcDEF123456789abcDEF123456789=\n+secret_key = s3cr3tvalue\n+other = keep\n")
    san.sanitize_file(c)
    t = c.read_text()
    assert "abcDEF" not in t and "s3cr3t" not in t and "+other = keep" in t


def test_sanitize_text_encoded_home_and_pytest_user():
    user = os.path.basename(os.path.expanduser("~"))
    t = san.sanitize_text(f"x/-Users-{user}--cache-y and pytest-of-{user}/pytest-1")
    assert user not in t and "-<home>" in t and "pytest-of-user" in t


def test_cli_check_and_rewrite(tmp_path, capsys):
    d = tmp_path / "res"
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({"x": "/Users/someone/repo/y"}))
    assert san.main([str(d), "--check", "--include-ignored"]) == 1
    assert san.main([str(d), "--include-ignored"]) == 0
    assert san.main([str(d), "--check", "--include-ignored"]) == 0


def _committable_results() -> list[Path]:
    res = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "--",
                          "evals/airflow/results"], cwd=REPO, capture_output=True, text=True)
    if res.returncode != 0:
        pytest.skip("not a git checkout")
    return [REPO / line for line in res.stdout.splitlines() if line and (REPO / line).is_file()]


def test_committable_results_have_no_local_paths():
    """Every result file git would commit is free of absolute /Users, /home and /private/tmp paths."""
    files = _committable_results()
    leaks = san.find_leaks(files)
    assert not leaks, "local paths in committable results (run evals/harness/sanitize.py):\n" + "\n".join(
        f"{p.relative_to(REPO)}:{i}: {s}" for p, i, s in leaks[:30])


def test_crash_and_backup_files_are_ignored():
    names = ["evals/airflow/results/x/runs.jsonl.harness-exception", "evals/airflow/results/x/runs.jsonl.prev-20260101",
             "evals/airflow/results/x/meta.json.bak", "evals/airflow/results/x/runs/c/m/run-1/attempt-0/sandbox.sb"]
    res = subprocess.run(["git", "check-ignore", "--no-index", *names], cwd=REPO, capture_output=True, text=True)
    assert sorted(res.stdout.split()) == sorted(names)


FAKE_TOKEN = "sk-ant-oat01-" + "Zx9_" * 12 + "-AAAA"


def test_redacts_anthropic_tokens_everywhere(tmp_path, monkeypatch):
    text = f"CLAUDE_CODE_OAUTH_TOKEN={FAKE_TOKEN} key='sk-ant-api03-abcDEF123456' {tmp_path}/x"
    out = san.sanitize_text(text, ())
    assert "sk-ant-" not in out and out.count(san.REDACTED) == 2
    assert san.dumps({"k": [FAKE_TOKEN]}).count(san.REDACTED) == 1
    # a token in the harness environment is redacted even without the sk-ant- prefix
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "opaque-token-value-1234567890")
    assert san.redact_secrets("env: opaque-token-value-1234567890") == f"env: {san.REDACTED}"


def test_redact_file_keeps_paths_and_find_leaks_flags_tokens(tmp_path):
    raw = tmp_path / "events.jsonl"
    raw.write_text(json.dumps({"cmd": "env", "out": f"TOKEN={FAKE_TOKEN}", "path": "/Users/me/x"}) + "\n")
    assert san.redact_file(raw) and not san.redact_file(raw)
    assert "sk-ant-" not in raw.read_text() and "/Users/me/x" in raw.read_text()
    leaky = tmp_path / "a.json"
    leaky.write_text(f'{{"t": "{FAKE_TOKEN}"}}\n')
    assert [x[2] for x in san.find_leaks([leaky])] == ["sk-ant-<secret>"]
    san.write_json(tmp_path / "b.json", {"t": FAKE_TOKEN})
    assert san.find_leaks([tmp_path / "b.json"]) == []
