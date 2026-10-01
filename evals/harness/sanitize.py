#!/usr/bin/env python3
"""Replace local absolute paths in committable eval artifacts.

Every writer in ``run_eval.py``, ``run_triggers.py`` and ``report.py`` passes
its output through :func:`sanitize_text` (or :func:`dumps`). Replacements, most
specific first:

- repo checkout (this worktree and the main checkout) -> ``<repo>``
- eval work root (``$EVAL_WORK_ROOT`` or ``~/.cache/des-evals/work``) -> ``<work>``
- temp roots (``$TMPDIR``, ``/var/folders/..``, ``/private/tmp``, ``/tmp``) -> ``<tmp>``
- the user's home -> ``~``; any other ``/Users/<name>`` or ``/home/<name>`` -> ``~``

Secrets are redacted first, in every file this module writes or rewrites:
``sk-ant-...`` tokens (Anthropic API keys and Claude Code OAuth tokens) and the
literal value of any :data:`SECRET_ENV_VARS` variable set in the harness's
environment, plus tokens fetched per attempt (:func:`register_secret`), become
``<redacted-secret>``. :func:`redact_file` applies only that
step to raw logs and transcripts (``events.jsonl``, ``stderr.log``).

CLI, for result dirs written before this existed::

    python3 evals/harness/sanitize.py evals/airflow/results [--check] [--include-ignored]

Only files git would commit are touched (``git check-ignore``), unless
``--include-ignored``. ``--check`` rewrites nothing and exits 1 if any file
still holds an absolute local path.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parents[1]
TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".patch", ".txt", ".log", ".yaml", ".yml", ".csv"}
#: What the committable-artifact test treats as a leaked local path.
LEAK_PATTERN = re.compile(r"(?<![\w.~<>-])/(?:Users|home)/[^/\s\"']+|(?<![\w.-])/(?:private/)?tmp/|"
                          r"(?<![\w.-])/(?:private/)?var/folders/")
_TEMP_PATTERNS = (
    re.compile(r"(?<![\w.-])/(?:private/)?var/folders/[^/\s\"']+/[^/\s\"']+/[A-Z](?=/|\b)"),
    re.compile(r"(?<![\w.-])/(?:private/)?tmp(?=/|\b)"),
    # Any other /var/folders reference (an agent's `ls /var/folders/`, a truncated path).
    re.compile(r"(?<![\w.-])/(?:private/)?var/folders(?=/|\b)"),
)
_OTHER_HOMES = re.compile(r"(?<![\w.~<>-])/(?:Users|home)/[^/\s\"']+")
#: Anthropic API keys (``sk-ant-api03-...``) and Claude Code OAuth tokens (``sk-ant-oat01-...``).
SECRET_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_-]{6,}")
#: Variables whose literal values are redacted wherever they appear.
SECRET_ENV_VARS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
REDACTED = "<redacted-secret>"
#: Randomly generated Airflow secrets that a config file written into a workspace holds.
_AIRFLOW_SECRET_LINE = re.compile(
    r"(?im)^([+\- ]?\s*(?:fernet_key|secret_key|jwt_secret|api_secret_key|internal_api_secret_key)\s*=\s*)\S.*$")
#: Binary-patch payloads (base85 blobs, e.g. a SQLite DB with local paths inside) up to the next file.
_BINARY_HUNK = re.compile(r"^GIT binary patch\n.*?(?=^diff --git |\Z)", re.M | re.S)
_OS_USER = re.compile(r"(?:-(?:Users|home)-|pytest-of-)" + re.escape(os.path.basename(os.path.expanduser("~")) or "\0"))
#: Literal secrets fetched at run time (per-attempt OAuth tokens), redacted like the env vars.
_RUNTIME_SECRETS: set[str] = set()


def register_secret(value: str) -> None:
    """Redact ``value`` from now on (tokens from ``EVAL_CLAUDE_TOKEN_CMD``)."""
    if value and len(value) >= 16:
        _RUNTIME_SECRETS.add(value)


def _git_common_root() -> str | None:
    try:
        res = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = res.stdout.strip()
    return str(Path(out).parent) if res.returncode == 0 and out else None


def _variants(path: str | os.PathLike | None) -> list[str]:
    if not path:
        return []
    p = os.path.normpath(os.path.expanduser(str(path)))
    out = [p, os.path.realpath(p)]
    return [x for i, x in enumerate(out) if x not in out[:i] and x not in ("/", "")]


@functools.lru_cache(maxsize=1)
def default_roots() -> tuple[tuple[str, str], ...]:
    """(path, replacement) pairs, longest path first within each group."""
    repo = _variants(REPO_ROOT) + _variants(_git_common_root())
    work = _variants(os.environ.get("EVAL_WORK_ROOT", "~/.cache/des-evals/work"))
    temp = _variants(tempfile.gettempdir()) + _variants(os.environ.get("TMPDIR"))
    home = _variants(os.path.expanduser("~"))
    pairs: list[tuple[str, str]] = []
    for group, label in ((repo, "<repo>"), (work, "<work>"), (temp, "<tmp>"), (home, "~")):
        for p in sorted(set(group), key=len, reverse=True):
            pairs.append((p, label))
    return tuple(pairs)


def redact_secrets(text: str) -> str:
    """``text`` with ``sk-ant-*`` tokens and the values of :data:`SECRET_ENV_VARS` redacted."""
    if not text:
        return text
    values = [os.environ.get(name) or "" for name in SECRET_ENV_VARS] + sorted(_RUNTIME_SECRETS)
    for val in values:
        if len(val) >= 16 and val in text:
            text = text.replace(val, REDACTED)
    return SECRET_PATTERN.sub(REDACTED, text)


def redact_file(path: str | os.PathLike) -> bool:
    """Redact secrets in a raw log/transcript in place (paths are left alone); True if it changed."""
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError:
        return False
    text = data.decode("utf-8", errors="surrogateescape")
    new = redact_secrets(text)
    if new == text:
        return False
    p.write_bytes(new.encode("utf-8", errors="surrogateescape"))
    return True


def sanitize_text(text: str, roots: Iterable[tuple[str, str]] | None = None) -> str:
    """``text`` with secrets redacted and local absolute paths replaced (see module docstring)."""
    if not text:
        return text
    text = redact_secrets(text)
    for path, label in (default_roots() if roots is None else roots):
        text = re.sub(re.escape(path) + r"(?=/|\b|$)", lambda _m, lab=label: lab, text)
    for rx in _TEMP_PATTERNS:
        text = rx.sub("<tmp>", text)
    text = _AIRFLOW_SECRET_LINE.sub(lambda m: m.group(1) + REDACTED, text)
    # Claude Code encodes a cwd as -Users-<name>-...; pytest names its temp dirs pytest-of-<name>.
    text = _OS_USER.sub(lambda m: "pytest-of-user" if m.group(0).startswith("pytest") else "-<home>", text)
    return _OTHER_HOMES.sub("~", text)


def scrub_patch(text: str) -> str:
    """``text`` with binary hunks replaced by a placeholder (their content cannot be sanitized)."""
    return _BINARY_HUNK.sub("Binary files differ (content omitted by sanitize.py)\n", text)


def sanitize_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return sanitize_text(obj)
    if isinstance(obj, list):
        return [sanitize_obj(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(sanitize_obj(x) for x in obj)
    if isinstance(obj, dict):
        return {sanitize_obj(k) if isinstance(k, str) else k: sanitize_obj(v) for k, v in obj.items()}
    return obj


def dumps(obj: Any, indent: int | None = 2) -> str:
    """``json.dumps`` of the sanitized object."""
    return json.dumps(sanitize_obj(obj), indent=indent)


def write_text(path: str | os.PathLike, text: str) -> None:
    Path(path).write_text(sanitize_text(text))


def write_json(path: str | os.PathLike, obj: Any) -> None:
    Path(path).write_text(dumps(obj))


def append_jsonl(path: str | os.PathLike, obj: Any) -> None:
    with Path(path).open("a") as fh:
        fh.write(dumps(obj, indent=None) + "\n")


def sanitize_file(path: str | os.PathLike) -> bool:
    """Rewrite a text file in place; returns True if it changed. Binary hunks of patches are dropped."""
    p = Path(path)
    try:
        text = p.read_text()
    except (UnicodeDecodeError, OSError):
        return False
    new = sanitize_text(scrub_patch(text) if p.suffix == ".patch" else text)
    if new != text:
        p.write_text(new)
        return True
    return False


def committable_files(root: Path, include_ignored: bool = False) -> list[Path]:
    """Text files under ``root`` that git would commit (all of them with ``include_ignored``)."""
    files = sorted(p for p in Path(root).rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES)
    if include_ignored or not files:
        return files
    ignored: set[str] = set()
    try:
        res = subprocess.run(["git", "check-ignore", "--stdin"], cwd=REPO_ROOT, capture_output=True, text=True,
                             input="\n".join(str(p.resolve()) for p in files), timeout=120)
        ignored = {os.path.normpath(x) for x in res.stdout.splitlines() if x.strip()}
    except (OSError, subprocess.TimeoutExpired):
        pass
    return [p for p in files if os.path.normpath(str(p.resolve())) not in ignored]


def find_leaks(files: Iterable[Path]) -> list[tuple[Path, int, str]]:
    out = []
    for p in files:
        try:
            lines = p.read_text().splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(lines, 1):
            m = LEAK_PATTERN.search(line)
            if m:
                out.append((p, i, m.group(0)))
            if SECRET_PATTERN.search(line):
                out.append((p, i, "sk-ant-<secret>"))
            if _OS_USER.search(line):
                out.append((p, i, "encoded home name"))
            if line.startswith("GIT binary patch"):
                out.append((p, i, "binary patch hunk"))
            m = _AIRFLOW_SECRET_LINE.match(line)
            if m and line[m.end(1):].strip() != REDACTED:
                out.append((p, i, "airflow secret value"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", type=Path)
    ap.add_argument("--check", action="store_true", help="report leaks, change nothing")
    ap.add_argument("--include-ignored", action="store_true", help="also process git-ignored files")
    args = ap.parse_args(argv)
    files = [f for d in args.dirs for f in committable_files(d, args.include_ignored)]
    if args.check:
        leaks = find_leaks(files)
        for p, i, s in leaks[:200]:
            print(f"{p}:{i}: {s}")
        print(f"{len(files)} files checked, {len(leaks)} leak(s)")
        return 1 if leaks else 0
    changed = sum(sanitize_file(f) for f in files)
    print(f"{len(files)} files scanned, {changed} rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
