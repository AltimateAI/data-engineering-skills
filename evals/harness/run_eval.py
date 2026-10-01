#!/usr/bin/env python3
"""Run Airflow skill evals with altimate-code or Claude Code and grade them deterministically.

Examples::

    # grader self-test, no LLM
    python3 evals/harness/run_eval.py --cases evals/airflow/cases --self-test

    # baseline arm, haiku, 3 runs per case, dev split
    python3 evals/harness/run_eval.py --cases evals/airflow/cases --arm baseline \
        --models google-vertex-anthropic/claude-haiku-4-5@20251001 --runs 3 \
        --parallel 4 --split dev --out evals/airflow/results/haiku-baseline-dev/

    # Claude Code on the user's subscription (CLAUDE_CODE_OAUTH_TOKEN or EVAL_CLAUDE_TOKEN_CMD)
    python3 evals/harness/run_eval.py --runner claude-code --arm skill --models claude-sonnet-5-5 \
        --split dev --out ~/.cache/des-evals/cc-skill-dev [--resume]

See evals/harness/README.md for the isolation model and the result layout.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import functools
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parents[1]
sys.path.insert(0, str(HARNESS_DIR))
import claude_code as cc  # noqa: E402
import grading as g  # noqa: E402
import isolation as iso  # noqa: E402
import sanitize as san  # noqa: E402

AREAS = ("authoring", "migration", "testing", "scheduling", "debugging")
SPLITS = ("dev", "holdout")
ARMS = ("baseline", "skill")
RUNNERS = ("altimate-code", "claude-code")
DEFAULT_MODELS = (
    "google-vertex-anthropic/claude-sonnet-5-5@default",
    "google-vertex-anthropic/claude-opus-5-5@default",
    "google-vertex-anthropic/claude-fable-5-1@default",
)
#: Default per-run cost cap (USD) by model key (``grading.model_key``), scaled to
#: each model's price so an expensive model is not cut off where a cheap one
#: finishes. Basis: the 122 Sonnet 4.6 task runs of 2026-09-30 re-priced per model
#: (mean / max per run: Sonnet 5.5 $1.22 / $3.52, Opus 5.5 $2.17 / $6.89,
#: Fable 5.1 $5.08 / $17.04); each cap clears that max even with ~1.35x more
#: tokens from the newer tokenizer. Sonnet 4.6's observed max was $5.27.
DEFAULT_RUN_CAP_USD = {
    "claude-haiku-4-5": 2.5,
    "claude-sonnet-4-6": 6.0,
    "claude-sonnet-5-5": 6.0,
    "claude-opus-5-5": 12.0,
    "claude-fable-5-1": 30.0,
}
FALLBACK_RUN_CAP_USD = 5.0
#: model used for altimate-code's auxiliary calls (titles, summaries) in every run.
SMALL_MODEL = "google-vertex-anthropic/claude-haiku-4-5@20251001"
STATUSES = ("ok", "task_fail", "timeout", "turn_limit", "cost_limit", "infra_error", "grader_error",
            "harness_error")
#: Final row statuses ``--resume`` runs again (nothing was graded).
RESUMABLE_STATUSES = ("infra_error", "harness_error", "skipped_budget", "skipped_usage_limit", "skipped_abort")
MAX_INFRA_RETRIES = 2
#: Retries after the agent process was killed from outside the harness (both runners).
MAX_KILLED_RETRIES = 2
#: Upper bounds for a case's ``timeout_s`` and ``max_turns`` (hard cases use the maximum).
MAX_CASE_TIMEOUT_S = 3600
MAX_CASE_TURNS = 120
#: Signals that mean "killed from outside" when the harness did not stop the run itself.
KILL_SIGNALS = (signal.SIGHUP, signal.SIGINT, signal.SIGKILL, signal.SIGTERM)
INFRA_PATTERNS = re.compile(
    r"rate.?limit|\b429\b|\b401\b|\b403\b|\b5\d\d\b|overloaded|quota|unauthori[sz]ed|"
    r"authenticat|token refresh|token (?:has )?expired|oauth token|invalid api key|/login\b|credential|ECONNRESET|ECONNREFUSED|ENOTFOUND|ETIMEDOUT|"
    r"socket hang up|fetch failed|network|service unavailable|internal server error|"
    r"provider.*(not found|error)|model.*not found|sdk\.responses",
    re.I,
)
#: infra errors a retry cannot fix: the model is not enabled for the project/account.
NON_RETRYABLE_INFRA = re.compile(
    r"Publisher model .* was not found|does not have access|PERMISSION_DENIED|data sharing to be enabled", re.I)


def should_retry(record: dict) -> bool:
    """Retry only infra errors that are not a missing model / permission problem."""
    return record.get("status") == "infra_error" and not NON_RETRYABLE_INFRA.search(
        " ".join([str(record.get("reason") or "")] + [str(e) for e in record.get("errors") or []]))
# Inherited variables that would change agent behaviour or leak host config.
AGENT_ENV_SCRUB_PREFIXES = ("AIRFLOW", "OPENCODE_", "ALTIMATE_ROUTER_")
AGENT_ENV_SCRUB_EXACT = ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "CONDA_PREFIX", "PYTHONUSERBASE",
                         "PIP_USER", "PIP_TARGET", "PIP_PREFIX", "UV_SYSTEM_PYTHON", "TMPDIR", "TMP", "TEMP",
                         "EVAL_CLAUDE_TOKEN_CMD")
#: Entries of the host's shared altimate-code data dir linked into each attempt's
#: private XDG_DATA_HOME: provider credentials and bundled binaries. Sessions,
#: traces and tool output stay per attempt, invisible to other runs.
ALTIMATE_DATA_LINKS = ("auth.json", "mcp-auth.json", "bin", "engine")
#: Host dirs with user-level skills/config that an agent must not read.
USER_SKILL_DIRS = ("~/.claude", "~/.agents", "~/.altimate-code", "~/.codex", "~/.opencode")
#: Host Claude Code user files a claude-code run must not read (its config dir is per attempt).
CLAUDE_USER_FILES = ("~/.claude.json", "~/.claude.json.backup", "~/CLAUDE.md", "~/AGENTS.md")

_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------


@dataclass
class Case:
    id: str
    dir: Path
    area: str
    split: str
    airflow_version: str
    prompt: str
    max_turns: int = 40
    timeout_s: int = 900
    grade_timeout_s: int = 900
    description: str = ""

    @property
    def fixture(self) -> Path:
        return self.dir / "fixture"

    @property
    def reference(self) -> Path:
        return self.dir / "reference"

    @property
    def alt_reference(self) -> Path | None:
        p = self.dir / "alt_reference"
        return p if p.is_dir() else None

    @property
    def mutants(self) -> list[Path]:
        root = self.dir / "mutants"
        return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []

    @property
    def grader(self) -> Path:
        return self.dir / "grade.py"

    @property
    def env_py(self) -> str:
        """Grader env interpreter (never visible to the agent)."""
        return g.env_python(self.airflow_version)

    @property
    def agent_env_py(self) -> str:
        """Interpreter of the agent's own Airflow venv."""
        return g.agent_env_python(self.airflow_version)


def load_case(case_dir: Path) -> Case:
    """Parse and validate ``case.yaml``; raises ``ValueError`` with every problem found."""
    data = yaml.safe_load((case_dir / "case.yaml").read_text()) or {}
    problems = []
    for key in ("id", "area", "split", "airflow_version", "prompt"):
        if not data.get(key):
            problems.append(f"missing {key}")
    if data.get("id") and data["id"] != case_dir.name:
        problems.append(f"id {data['id']!r} != directory name {case_dir.name!r}")
    if data.get("area") and data["area"] not in AREAS:
        problems.append(f"area must be one of {AREAS}")
    if data.get("split") and data["split"] not in SPLITS:
        problems.append(f"split must be one of {SPLITS}")
    version = str(data.get("airflow_version", ""))
    if version and version not in g.ENV_DIRS:
        problems.append(f"airflow_version must be one of {sorted(g.ENV_DIRS)} (quote it in YAML)")
    for sub in ("fixture", "reference"):
        if not (case_dir / sub).is_dir():
            problems.append(f"missing {sub}/")
    if not (case_dir / "grade.py").is_file():
        problems.append("missing grade.py")
    for key, default, top in (("timeout_s", 900, MAX_CASE_TIMEOUT_S), ("max_turns", 40, MAX_CASE_TURNS)):
        try:
            val = int(data.get(key, default))
        except (TypeError, ValueError):
            problems.append(f"{key} must be an integer")
            continue
        if not 1 <= val <= top:
            problems.append(f"{key} must be between 1 and {top}, got {val}")
    if problems:
        raise ValueError(f"{case_dir}: " + "; ".join(problems))
    return Case(
        id=data["id"],
        dir=case_dir.resolve(),
        area=data["area"],
        split=data["split"],
        airflow_version=version,
        prompt=str(data["prompt"]).strip(),
        max_turns=int(data.get("max_turns", 40)),
        timeout_s=int(data.get("timeout_s", 900)),
        grade_timeout_s=int(data.get("grade_timeout_s", 900)),
        description=str(data.get("description", "")).strip(),
    )


def discover_cases(root: Path, split: str = "all", ids: list[str] | None = None) -> list[Case]:
    """Cases under ``root``. Ids starting with ``_`` (examples) run only when named in ``ids``."""
    cases = []
    for d in sorted(p for p in root.iterdir() if (p / "case.yaml").is_file()):
        if ids and d.name not in ids:
            continue
        if not ids and d.name.startswith("_"):
            continue
        c = load_case(d)
        if split != "all" and c.split != split:
            continue
        cases.append(c)
    if ids:
        missing = set(ids) - {c.id for c in cases}
        if missing:
            raise SystemExit(f"unknown or filtered-out case ids: {sorted(missing)}")
    return cases


_HASH_IGNORE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git"}
_HASH_IGNORE_FILES = {".DS_Store"}


def hash_dir(path: Path) -> str:
    """sha256 over sorted relative paths and file bytes (caches ignored)."""
    h = hashlib.sha256()
    if not path.exists():
        return "missing"
    for p in sorted(path.rglob("*")):
        rel = p.relative_to(path)
        if any(part in _HASH_IGNORE_DIRS for part in rel.parts) or p.name in _HASH_IGNORE_FILES:
            continue
        if p.suffix == ".pyc" or not p.is_file():
            continue
        h.update(rel.as_posix().encode() + b"\0")
        h.update(p.read_bytes() + b"\0")
    return h.hexdigest()


# --------------------------------------------------------------------------
# Workspaces
# --------------------------------------------------------------------------


def find_enclosing_git(path: Path) -> Path | None:
    for p in [path, *path.parents]:
        if (p / ".git").exists():
            return p
    return None


def work_root() -> Path:
    root = Path(os.environ.get("EVAL_WORK_ROOT", "~/.cache/des-evals/work")).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    repo = find_enclosing_git(root)
    if repo:
        raise SystemExit(f"EVAL_WORK_ROOT {root} is inside git repo {repo}; choose a path outside any repo")
    return root


def git(ws: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.name=eval", "-c", "user.email=eval@example.invalid",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=ws, capture_output=True, text=True, check=False,
    )


def make_workspace(case: Case, overlays: list[Path], parent: Path) -> Path:
    """Fixture (+ overlays) copied to ``parent/ws`` and committed as the initial state."""
    ws = parent / "ws"
    if ws.exists():
        shutil.rmtree(ws)
    shutil.copytree(case.fixture, ws, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    for ov in overlays:
        g.apply_overlay(ov, ws)
    git(ws, "init", "-q", "-b", "main")
    git(ws, "add", "-A")
    git(ws, "commit", "-q", "-m", "initial project state")
    return ws


# airflow.cfg / airflow.db appear when an agent points AIRFLOW_HOME at its workspace; they hold random
# secrets and absolute paths, not the agent's work.
_PATCH_IGNORE = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".DS_Store", "airflow.cfg", "airflow.db",
                                       "webserver_config.py")


def workspace_patch(ws: Path, base: Path, scratch: Path) -> str:
    """Text diff from ``base`` (the fixture) to the agent's final workspace.

    Built in a fresh repo under ``scratch`` so nothing in the agent-controlled
    ``ws/.git`` (config filters, fsmonitor, hooks) runs in the unsandboxed harness.
    Symlinks are copied as links, never followed.
    """
    repo = scratch / "patch-repo"
    if repo.exists():
        shutil.rmtree(repo)
    shutil.copytree(base, repo, ignore=_PATCH_IGNORE, symlinks=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", "base")
    for child in repo.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(ws, repo, ignore=_PATCH_IGNORE, symlinks=True, dirs_exist_ok=True)
    git(repo, "add", "-A")
    return git(repo, "diff", "--cached", "HEAD").stdout


def escaping_symlinks(ws: Path) -> list[str]:
    """External or otherwise unsafe links that cannot be passed to a grader."""
    return g.unsafe_workspace_symlinks(ws)


# --------------------------------------------------------------------------
# Skills staging and inventory
# --------------------------------------------------------------------------


def skill_names(skills_dir: Path) -> list[str]:
    """``name`` frontmatter of every SKILL.md under ``skills_dir``."""
    names = []
    for md in sorted(skills_dir.rglob("SKILL.md")) if skills_dir.exists() else []:
        fm = parse_frontmatter(md.read_text())
        if fm.get("name"):
            names.append(str(fm["name"]))
    return names


def parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def stage_skills(arm: str, repo_skills: Path, airflow_skills: Path, dest: Path) -> Path:
    """Copy repo skills (minus ``airflow/``) to ``dest``; the skill arm also gets ``airflow/``.

    Agents only ever see this copy, never the repo checkout (graders live there).
    """
    if dest.exists():
        shutil.rmtree(dest)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")

    def top_ignore(src: str, names: list[str]) -> set[str]:
        skip = set(ignore(src, names))
        if Path(src).resolve() == repo_skills.resolve():
            skip.add("airflow")
        return skip

    shutil.copytree(repo_skills, dest, ignore=top_ignore)
    if arm == "skill":
        if not airflow_skills.is_dir():
            raise SystemExit(f"--skills-dir {airflow_skills} does not exist")
        shutil.copytree(airflow_skills, dest / "airflow", ignore=ignore)
    return dest


def host_altimate_data_dir(base: dict[str, str] | None = None) -> Path:
    """The host's shared altimate-code data dir (``$XDG_DATA_HOME/altimate-code``)."""
    src = os.environ if base is None else base
    data = src.get("XDG_DATA_HOME") or os.path.join(src.get("HOME", os.path.expanduser("~")), ".local", "share")
    return Path(data) / "altimate-code"


def host_altimate_cache_dir(base: dict[str, str] | None = None) -> Path:
    src = os.environ if base is None else base
    cache = src.get("XDG_CACHE_HOME") or os.path.join(src.get("HOME", os.path.expanduser("~")), ".cache")
    return Path(cache) / "altimate-code"


def grader_env_dirs() -> list[Path]:
    return [g.env_root() / name for name in g.ENV_DIRS.values()]


def _clean_path(path: str, drop: list[Path]) -> str:
    """``PATH`` without entries inside any of ``drop`` (grader venvs, a stale VIRTUAL_ENV)."""
    drop_s = [os.path.realpath(str(d)) for d in drop]
    keep = []
    for entry in path.split(os.pathsep):
        if not entry:
            continue
        real = os.path.realpath(os.path.expanduser(entry))
        if any(real == d or real.startswith(d + os.sep) for d in drop_s):
            continue
        keep.append(entry)
    return os.pathsep.join(keep)


def build_agent_env(
    attempt_dir: Path, workspace: Path, skills_dir: Path, env_py: str, base: dict[str, str] | None = None
) -> dict[str, str]:
    """Environment for one altimate-code run; every writable location is under ``attempt_dir``.

    - ``OPENCODE_TEST_HOME``: fresh empty dir (no ~/.claude, ~/.agents, ~/.altimate-code).
    - ``XDG_CONFIG_HOME``: fresh empty dir (no user config.json, agents or kits).
    - ``XDG_DATA_HOME`` / ``XDG_STATE_HOME``: per attempt, so sessions, traces and tool
      output of other runs are not on disk where the agent looks. The host's
      ``auth.json``, ``bin`` and ``engine`` are symlinked in; Vertex also uses the
      inherited ``GOOGLE_*``/``VERTEX_*`` variables.
    - ``TMPDIR``/``TMP``/``TEMP``: ``<attempt>/tmp``, never the shared ``/tmp``.
    - ``OPENCODE_DISABLE_EXTERNAL_SKILLS=1`` and skills only from ``skills_dir`` via
      ``OPENCODE_CONFIG_CONTENT``.
    - ``env_py``'s venv (the agent env, never a grader env) is "activated" (PATH/VIRTUAL_ENV)
      with a private AIRFLOW_HOME and dags_folder=<workspace>/dags, identical in both arms.
      Grader venvs and any inherited VIRTUAL_ENV are removed from PATH.
    - pip: ``PIP_REQUIRE_VIRTUALENV=1`` (a global pip on PATH refuses to install),
      ``PYTHONUSERBASE`` and pip/uv caches per attempt.
    """
    src = dict(os.environ if base is None else base)
    env = {
        k: v
        for k, v in src.items()
        if not k.startswith(AGENT_ENV_SCRUB_PREFIXES) and k not in AGENT_ENV_SCRUB_EXACT
    }
    venv = Path(env_py).parent.parent
    if any(os.path.realpath(venv) == os.path.realpath(d) for d in grader_env_dirs()):
        raise ValueError(f"{venv} is a grader env; agents must use the agent env (g.agent_env_python)")
    dirs = {name: attempt_dir / name for name in (
        "agent-home", "agent-xdg-config", "agent-xdg-data", "agent-xdg-state", "agent-airflow-home", "tmp",
        "agent-pyuser", "agent-pip-cache", "agent-uv-cache")}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    host_data = host_altimate_data_dir(src)
    data = dirs["agent-xdg-data"] / "altimate-code"
    data.mkdir(exist_ok=True)
    for name in ALTIMATE_DATA_LINKS:
        if (host_data / name).exists() and not (data / name).exists():
            (data / name).symlink_to(host_data / name)
    config = {
        "$schema": "https://altimate.ai/config.json",
        "skills": {"paths": [str(skills_dir)]},
        "small_model": SMALL_MODEL,
        "autoupdate": False,
        "share": "disabled",
    }
    drop = grader_env_dirs() + ([Path(src["VIRTUAL_ENV"])] if src.get("VIRTUAL_ENV") else [])
    tmp = str(dirs["tmp"])
    env.update(
        {
            "OPENCODE_TEST_HOME": str(dirs["agent-home"]),
            "XDG_CONFIG_HOME": str(dirs["agent-xdg-config"]),
            "XDG_DATA_HOME": str(dirs["agent-xdg-data"]),
            "XDG_STATE_HOME": str(dirs["agent-xdg-state"]),
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
            "OPENCODE_CONFIG_CONTENT": json.dumps(config),
            "TMPDIR": tmp,
            "TMP": tmp,
            "TEMP": tmp,
            "VIRTUAL_ENV": str(venv),
            "PATH": os.pathsep.join((str(venv / "bin"), _clean_path(env.get("PATH", ""), drop))),
            "PIP_REQUIRE_VIRTUALENV": "1",
            "PIP_CACHE_DIR": str(dirs["agent-pip-cache"]),
            "UV_CACHE_DIR": str(dirs["agent-uv-cache"]),
            "PYTHONUSERBASE": str(dirs["agent-pyuser"]),
            "AIRFLOW_HOME": str(dirs["agent-airflow-home"]),
            "AIRFLOW__CORE__DAGS_FOLDER": str(workspace / "dags"),
            "AIRFLOW__CORE__LOAD_EXAMPLES": "False",
            "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
            "no_proxy": "*",
            "NO_PROXY": "*",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env


@functools.lru_cache(maxsize=1)
def main_repo_root() -> Path | None:
    """The main checkout when REPO_ROOT is a git worktree (graders live there too)."""
    res = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO_ROOT,
                         capture_output=True, text=True)
    out = res.stdout.strip()
    return Path(out).parent if res.returncode == 0 and out else None


@dataclass
class IsolationRoots:
    """Paths an agent run is fenced off from, plus the holes it needs."""

    scratch: Path
    agent_venv: Path
    staged_skills: Path
    out_dir: Path | None
    work_root: Path
    base: dict[str, str] | None = None
    runner: str = "altimate-code"

    def forbidden(self) -> list[tuple[str, str]]:
        src = os.environ if self.base is None else self.base
        home = src.get("HOME", os.path.expanduser("~"))
        roots = [("shared-temp", t) for t in iso.SHARED_TEMP_ROOTS]
        roots += [("repo", str(REPO_ROOT))]
        main = main_repo_root()
        if main:
            roots.append(("repo", str(main)))
        if self.out_dir:
            roots.append(("results", str(self.out_dir)))
        # Campaign outputs are also commonly stored beside the venvs. Fence off
        # all older campaigns there, including when EVAL_ENV_ROOT is overridden.
        roots.append(("eval-cache", str(Path(home) / ".cache" / "des-evals")))
        roots.append(("eval-cache", str(g.env_root())))
        if self.out_dir:
            # Custom output locations can share a parent with older campaigns.
            # Deny the campaign dirs, not an arbitrary parent such as HOME or /.
            parent = self.out_dir.resolve().parent
            if parent.is_dir():
                for p in parent.iterdir():
                    try:
                        if p.is_dir() and ((p / "meta.json").is_file() or (p / "runs.jsonl").is_file()):
                            roots.append(("results", str(p)))
                    except OSError:
                        continue  # unrelated virtual or inaccessible filesystem entries
        roots.append(("work-root", str(self.work_root)))
        roots.append(("altimate-data", str(host_altimate_data_dir(self.base))))
        roots += [("user-skills", d.replace("~", home, 1)) for d in USER_SKILL_DIRS]
        if self.runner == "claude-code":
            roots += [("user-config", f.replace("~", home, 1)) for f in CLAUDE_USER_FILES]
        roots += [("grader-env", str(d)) for d in grader_env_dirs()]
        return roots

    def allowed(self) -> list[str]:
        return [str(self.scratch), str(self.staged_skills), str(self.agent_venv)]

    def policy(self) -> iso.ContaminationPolicy:
        src = os.environ if self.base is None else self.base
        return iso.ContaminationPolicy(self.forbidden(), self.allowed(), src.get("HOME", os.path.expanduser("~")))

    def sandbox_profile(self) -> str:
        """Writes only under scratch, the agent venv, altimate-code's cache and /dev; no
        reads of the repo, results, other attempts, shared altimate-code data or user skills."""
        host_data = host_altimate_data_dir(self.base)
        read_deny = [p for label, p in self.forbidden() if label not in ("shared-temp", "grader-env")]
        # Shared temp dirs where graders and older runs leave outputs. /var/folders/*/C
        # (per-user caches some macOS frameworks need) stays readable.
        read_deny += ["/private/tmp", "/private/var/tmp", tempfile.gettempdir()]
        # Runtime packages remain readable, as before; grader venv references
        # still count as contamination in the transcript policy.
        runtime_dirs = [self.agent_venv, *grader_env_dirs()]
        metadata_paths = {str(p) for root in [self.scratch, *runtime_dirs]
                          for p in Path(os.path.realpath(root)).parents}
        if self.runner == "claude-code":
            # Claude Code keeps config, sessions and its temp files under the attempt
            # scratch dir (CLAUDE_CONFIG_DIR, CLAUDE_CODE_TMPDIR); it needs no host data.
            # Ancestors of the scratch dir (inside the denied work root) stay stat-able:
            # without it `mkdir -p <ws>/x` and SQLite (Airflow's metadata DB) fail.
            return iso.sandbox_profile(
                write_allow=[self.scratch, self.agent_venv, "/dev"],
                read_deny=read_deny,
                read_allow=[self.scratch, self.staged_skills, *runtime_dirs],
                read_allow_literal=cc.binary_paths(),
                metadata_allow_literal=sorted(metadata_paths),
            )
        links = [host_data / n for n in ALTIMATE_DATA_LINKS if (host_data / n).exists()]
        return iso.sandbox_profile(
            write_allow=[self.scratch, self.agent_venv, host_altimate_cache_dir(self.base), "/dev"],
            read_deny=read_deny,
            read_allow=[self.scratch, self.staged_skills, *runtime_dirs] + [p for p in links if p.is_dir()],
            read_allow_literal=[p for p in links if not p.is_dir()],
            metadata_allow_literal=sorted(metadata_paths),
        )


def list_skills(env: dict[str, str], cwd: Path) -> list[dict]:
    res = subprocess.run(["altimate-code", "skill", "list", "--json"], env=env, cwd=cwd,
                         capture_output=True, text=True, timeout=180)
    out = res.stdout
    start = out.find("[")
    if res.returncode != 0 or start < 0:
        raise RuntimeError(f"skill list failed rc={res.returncode}: {res.stderr[-800:]}")
    return json.loads(out[start:])


def check_inventory(arm: str, inventory: list[dict], staged: Path, airflow_names: list[str],
                    repo_names: list[str]) -> list[str]:
    """Problems with a skill inventory (empty list = OK). Pure; unit-tested."""
    problems = []
    by_name = {s.get("name"): s for s in inventory}
    for n in repo_names:
        if n not in by_name:
            problems.append(f"repo skill {n!r} missing")
    for n in airflow_names:
        present = n in by_name
        if arm == "skill" and not present:
            problems.append(f"airflow skill {n!r} missing in skill arm")
        if arm == "baseline" and present:
            problems.append(f"airflow skill {n!r} present in baseline arm")
    staged_s = str(staged.resolve())
    repo_s = str(REPO_ROOT)
    for s in inventory:
        loc = str(s.get("location") or "")
        if loc.startswith(repo_s):
            problems.append(f"skill {s.get('name')!r} loaded from repo checkout {loc}")
        if arm == "baseline" and "/airflow/" in loc and loc.startswith(staged_s):
            problems.append(f"baseline loads {loc}")
    return problems


# --------------------------------------------------------------------------
# Budget
# --------------------------------------------------------------------------


class Budget:
    def __init__(self, cap_usd: float) -> None:
        self.cap = cap_usd
        self.spent = 0.0
        self.stopped = False
        self._lock = threading.Lock()

    def can_launch(self) -> bool:
        with self._lock:
            if self.spent >= self.cap:
                if not self.stopped:
                    log(f"BUDGET: campaign cap ${self.cap:.2f} reached (spent ${self.spent:.2f}); no new runs")
                self.stopped = True
                return False
            return True

    def add(self, usd: float) -> None:
        with self._lock:
            self.spent += usd


# --------------------------------------------------------------------------
# One attempt
# --------------------------------------------------------------------------


def classify_attempt(
    *,
    timed_out: bool,
    cost_capped: bool,
    returncode: int | None,
    events: list[dict],
    stderr: str,
    grade: dict | None,
    grader_failed: bool,
) -> tuple[str, str]:
    """Attempt status + reason. Pure; unit-tested.

    Infra problems win (they are retried); otherwise a passing grade is ``ok``
    even if the agent hit a limit, and a failing one is attributed to the limit
    (timeout / turn_limit / cost_limit) or to the task. A run killed by a signal
    the harness did not send (no final result/termination event) is ``infra_error``
    with a reason starting ``killed``.
    """
    steps = g.model_steps(events)
    errors = g.error_messages(events)
    term = g.termination(events) or {}
    if not timed_out and not cost_capped:
        sig = kill_signal(returncode)
        if sig is not None and not term:
            return "infra_error", f"killed by signal {sig} ({signal.Signals(sig).name}), rc={returncode}"
        if not steps:
            detail = (" | ".join(errors) or stderr.strip()[-400:] or f"rc={returncode}, no events")
            return "infra_error", f"no model steps completed: {detail[:500]}"
        infra_errs = [e for e in errors if INFRA_PATTERNS.search(e) or cc.USAGE_LIMIT.search(e)]
        if infra_errs and term.get("why_harness_stopped") == "error":
            return "infra_error", infra_errs[-1][:500]
    if grader_failed or grade is None:
        return "grader_error", "grade.py crashed or wrote no valid result"
    if grade.get("primary_pass"):
        return "ok", "primary checks passed"
    if timed_out:
        return "timeout", "wall-clock timeout"
    if cost_capped:
        return "cost_limit", "per-run cost cap"
    if term.get("why_harness_stopped") == "budget-exhausted":
        return "turn_limit", "max turns reached"
    failed = [c["name"] for c in grade.get("checks", []) if c["kind"] == "primary" and not c["passed"]]
    return "task_fail", "failed primary: " + ", ".join(failed)[:500]


def kill_signal(returncode: int | None) -> int | None:
    """The kill signal behind a return code: ``-N`` (Popen) or ``128+N`` (shell/node), else None."""
    if returncode is None:
        return None
    sig = -returncode if returncode < 0 else returncode - 128 if returncode > 128 else None
    return sig if sig in KILL_SIGNALS else None


def is_killed(record: dict) -> bool:
    return record.get("status") == "infra_error" and str(record.get("reason") or "").startswith("killed")


def _stream_cost(path: Path, offset: int, model: str | None = None, correct: bool = True) -> tuple[float, int]:
    """Cost from step_finish events appended to ``path`` since ``offset`` (see ``grading.step_cost``)."""
    cost = 0.0
    try:
        with path.open("rb") as fh:
            fh.seek(offset)
            data = fh.read()
    except FileNotFoundError:
        return 0.0, offset
    end = data.rfind(b"\n")
    if end < 0:
        return 0.0, offset
    for line in data[: end + 1].splitlines():
        if b'"step_finish"' not in line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        cost += g.step_cost(e.get("part") or {}, model, correct)
    return cost, offset + end + 1


def run_cap_for(model: str, overrides: dict[str, float] | None, flat: float | None) -> float:
    """Per-run cost cap for ``model``: ``--max-run-cost-usd-by-model`` entry (full id or
    model key), else ``--max-run-cost-usd``, else ``DEFAULT_RUN_CAP_USD``, else the fallback."""
    overrides = overrides or {}
    for key in (model, g.model_key(model)):
        if key in overrides:
            return overrides[key]
    if flat is not None:
        return flat
    return DEFAULT_RUN_CAP_USD.get(g.model_key(model), FALLBACK_RUN_CAP_USD)


def parse_cap_map(text: str | None) -> dict[str, float]:
    """``"model=usd,model2=usd"`` -> dict; raises ``ValueError`` on malformed entries."""
    out: dict[str, float] = {}
    for item in (text or "").split(","):
        if not item.strip():
            continue
        key, sep, val = item.rpartition("=")
        if not sep or not key.strip():
            raise ValueError(f"bad cap entry {item!r}; expected MODEL=USD")
        out[key.strip()] = float(val)
    return out


def run_agent_process(cmd: list[str], cwd: Path, env: dict[str, str], events_path: Path, stderr_path: Path,
                      timeout_s: float, cap_usd: float | None, model: str, correct: bool,
                      spool_dir: Path | None = None, monitor_factory=None) -> dict:
    """Run the agent, streaming cost; stop it on timeout or cost cap. The process
    group is always stopped, even if monitoring raises.

    With ``spool_dir``, stdout/stderr go to files there and are copied to
    ``events_path``/``stderr_path`` afterwards: under the sandbox the results dir
    is unreadable, and node aborts at startup when its stdio is a file it cannot read.
    Secrets (``sk-ant-*``, the OAuth token) are redacted in both copies.

    ``monitor_factory(out_path)`` (Claude Code) returns a :class:`claude_code.StreamMonitor`
    that replaces the altimate-code cost reader. Its ``abort_reason`` (inventory
    mismatch at the init event) stops the run and is returned as ``aborted``.
    """
    started = time.time()
    out_path = spool_dir / "events.jsonl" if spool_dir else events_path
    err_path = spool_dir / "stderr.log" if spool_dir else stderr_path
    flags = {"timed_out": False, "cost_capped": False, "returncode": None, "aborted": None}
    monitor = monitor_factory(out_path) if monitor_factory else None
    try:
        _run_and_watch(cmd, cwd, env, out_path, err_path, started, timeout_s, cap_usd, model, correct, flags,
                       monitor)
    finally:
        if spool_dir:
            for src, dst in ((out_path, events_path), (err_path, stderr_path)):
                if src.exists():
                    shutil.copyfile(src, dst)
        for p in {out_path, err_path, events_path, stderr_path}:
            if p.exists():
                san.redact_file(p)
    out = {**flags, "wall_s": round(time.time() - started, 1)}
    if monitor is not None:
        out.update({"inventory": monitor.inventory, "inventory_problems": monitor.inventory_problems})
    return out


def _run_and_watch(cmd, cwd, env, out_path: Path, err_path: Path, started: float, timeout_s: float,
                   cap_usd: float | None, model: str, correct: bool, flags: dict, monitor=None) -> None:
    timed_out = cost_capped = False
    aborted = None
    with out_path.open("wb") as out_fh, err_path.open("wb") as err_fh:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=out_fh, stderr=err_fh,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            run_cost, offset = 0.0, 0
            while proc.poll() is None:
                time.sleep(2)
                if monitor is not None:
                    run_cost = monitor.poll()
                    aborted = monitor.abort_reason
                else:
                    c, offset = _stream_cost(out_path, offset, model, correct)
                    run_cost += c
                if time.time() - started > timeout_s:
                    timed_out = True
                elif cap_usd and run_cost > cap_usd:
                    cost_capped = True
                if timed_out or cost_capped or aborted:
                    stop_process_group(proc)
                    break
        finally:
            # A successful leader can leave grandchildren running. Reap the whole
            # group before any workspace reads, environment restores or grading.
            stop_process_group(proc, grace_s=0 if (timed_out or cost_capped or aborted) else 5)
            proc.wait()
            if monitor is not None:
                monitor.poll()
                aborted = aborted or monitor.abort_reason
            flags.update({"timed_out": timed_out, "cost_capped": cost_capped, "returncode": proc.returncode,
                          "aborted": aborted})


def auto_loaded_skills(trace_path: str | None) -> list[str]:
    if not trace_path or not Path(trace_path).exists():
        return []
    try:
        text = Path(trace_path).read_text(errors="replace")
    except OSError:
        return []
    return sorted(set(re.findall(r'<auto_loaded_skill name=\\?"([^"\\]+)', text)))


def attempt_artifact(path: str | Path, scratch: Path) -> Path:
    """Resolve agent-selected artifact paths without reading outside the attempt."""
    try:
        resolved = Path(path).resolve()
    except (OSError, RuntimeError) as exc:
        raise g.UnsafeWorkspaceError("unsafe attempt artifact path") from exc
    if not resolved.is_relative_to(scratch.resolve()):
        raise g.UnsafeWorkspaceError("attempt artifact points outside scratch")
    return resolved


def stop_process_group(proc: subprocess.Popen, grace_s: float = 15) -> None:
    """SIGTERM the agent's process group, then SIGKILL after ``grace_s``.

    Wait for the group, not just its leader: descendants may ignore SIGTERM.
    """
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        proc.poll()  # reap the leader if it has exited
        try:
            os.killpg(proc.pid, 0)
        except OSError:
            return
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass


def run_grader(case: Case, workspace: Path, events: Path, out: Path, log_path: Path) -> tuple[dict | None, bool]:
    g.validate_workspace(workspace)
    env = cc.scrub_env(g.scrubbed_environ())
    env.pop(cc.TOKEN_VAR, None)  # graders never need the agent's credentials
    env.pop(cc.TOKEN_CMD_VAR, None)
    env.update({"EVAL_HARNESS_DIR": str(HARNESS_DIR), "EVAL_CASE_DIR": str(case.dir),
                "PYTHONDONTWRITEBYTECODE": "1"})
    if out.exists():
        out.unlink()
    workspace, events, out, log_path = (Path(p).resolve() for p in (workspace, events, out, log_path))
    res = g.run_cmd([case.env_py, str(case.grader), "--workspace", str(workspace), "--events", str(events),
                     "--out", str(out)], env=env, cwd=case.dir, timeout=case.grade_timeout_s)
    log_path.write_text(san.redact_secrets(res.output))
    if out.exists():
        san.sanitize_file(out)  # check details can quote workspace / temp paths, even on failure
    if res.timed_out or res.returncode != 0 or not out.exists():
        return None, True
    try:
        data = json.loads(out.read_text())
    except ValueError:
        return None, True
    if not isinstance(data, dict) or "primary_pass" not in data or "checks" not in data:
        return None, True
    return data, False


@dataclass
class AttemptContext:
    """Per-campaign settings shared by every attempt (built in ``main``)."""

    out_dir: Path | None
    work_dir: Path
    staged_skills: Path
    altimate_version: str = ""
    sandbox: bool = False
    env_guards: dict[str, iso.AgentEnvGuard] = field(default_factory=dict)
    run_caps: dict[str, float] = field(default_factory=dict)
    runner: str = "altimate-code"
    #: claude-code: the arm's skills flattened to ``<name>/SKILL.md`` (copied into each
    #: attempt's CLAUDE_CONFIG_DIR/skills) and the arm spec its inventory must match.
    flat_skills: Path | None = None
    arm: str = ""
    airflow_names: list[str] = field(default_factory=list)
    repo_names: list[str] = field(default_factory=list)
    runner_version: str = ""
    usage_gate: cc.UsageLimitGate | None = None
    #: set when an attempt finds a broken setup (inventory mismatch): no new attempts start.
    abort_reason: str | None = None
    #: skills of the validated campaign inventory; an attempt's init event may not add any
    #: (e.g. project skills shipped in a fixture's .claude/skills).
    expected_skills: list[str] | None = None

    def check_inventory(self, inv: dict | None) -> list[str]:
        problems = cc.check_inventory(self.arm, inv, self.airflow_names, self.repo_names)
        if inv is not None and self.expected_skills is not None:
            extra = sorted(set(inv.get("skills") or []) - set(self.expected_skills))
            if extra:
                problems.append(f"skills not in the campaign inventory: {extra}")
        return problems


def isolation_report(events: list[dict], roots: IsolationRoots) -> dict:
    """Contamination scan of a run's tool calls (see ``isolation.scan_contamination``), plus
    ``kill_commands``: bash calls that kill processes by name or pattern (``scan_kill_commands``)."""
    calls = g.tool_uses(events)
    out = iso.scan_contamination(calls, roots.policy())
    out["kill_commands"] = iso.scan_kill_commands(calls)
    return out


def attempt_cap(ctx: AttemptContext | None, model: str, flat: float | None) -> float | None:
    """The campaign's cap for ``model`` (0 = no cap); ``flat`` only when the model has no entry."""
    caps = ctx.run_caps if ctx else {}
    return caps[model] if model in caps else flat


def recover_usage(record: dict, paths: list[Path], model: str, correct: bool) -> None:
    """Fill usage/cost from whichever events file exists when an exception hit before accounting."""
    if record.get("cost_usd") or not record.get("launched"):
        return
    for p in paths:
        if p.exists():
            use = g.usage(g.load_events(p), model, correct)
            record.update({"cost_usd": use["cost_usd"], "cost_reported_usd": use["cost_reported_usd"],
                           "tokens": use["tokens"], "steps": use["steps"], "usage_recovered_from": p.name})
            return


def _guard_check(ctx: AttemptContext | None, version: str, raise_on_fail: bool = True) -> dict | None:
    """Check/restore the agent venv. A failed restore before launch raises, so no run
    starts on a dirty env (``harness_error``, $0); after a run it is only recorded."""
    guard = (ctx.env_guards if ctx else {}).get(version)
    if guard is None:
        return None
    res = guard.check()
    if res["changed"]:
        log(f"AGENT ENV {guard.venv.name} changed: restored={res['restored']} {res['detail']}")
        if not res["restored"] and raise_on_fail:
            raise RuntimeError(f"agent env {guard.venv} changed and could not be restored: {res['detail']}")
    return res


def prepare_agent(case_id: str, agent_py: str, fixture_ws, prompt: str, model: str, max_turns: int,
                  skills_dir: Path, args: argparse.Namespace, env_hook=None) -> dict:
    """Scratch dir, workspace, env, sandbox profile and command for one agent run.

    ``fixture_ws(scratch) -> workspace``; ``env_hook(env) -> env`` adjusts the agent env.
    """
    ctx: AttemptContext | None = getattr(args, "ctx", None)
    scratch = Path(tempfile.mkdtemp(prefix=f"{case_id}-", dir=args.work_dir))
    ws = fixture_ws(scratch)
    env = build_agent_env(scratch, ws, skills_dir, agent_py)
    runner = ctx.runner if ctx else "altimate-code"
    if runner == "claude-code":
        if ctx is None or ctx.flat_skills is None:
            raise ValueError("claude-code runner needs AttemptContext.flat_skills")
        config_dir, mcp = cc.prepare_config_dir(scratch, ctx.flat_skills)
        try:
            env = cc.agent_env(env, config_dir)
        except cc.TokenCommandError:
            shutil.rmtree(scratch, ignore_errors=True)
            raise
        cmd = cc.command(model, max_turns, prompt, mcp)
    else:
        cmd = ["altimate-code", "run", "--format", "json", "-m", model, "--max-turns", str(max_turns),
               "--yolo", "--dir", str(ws), "-o", str(scratch / "final.md"), prompt]
    if env_hook:
        env = env_hook(env)
    roots = IsolationRoots(scratch=scratch, agent_venv=Path(agent_py).parent.parent,
                           staged_skills=skills_dir, out_dir=ctx.out_dir if ctx else None,
                           work_root=Path(os.environ.get("EVAL_WORK_ROOT", "~/.cache/des-evals/work")).expanduser(),
                           runner=runner)
    if ctx and ctx.sandbox:
        profile = scratch / "sandbox.sb"
        profile.write_text(roots.sandbox_profile())
        cmd = iso.sandbox_wrap(cmd, profile)
    return {"scratch": scratch, "ws": ws, "env": env, "roots": roots, "cmd": cmd}


class AttemptAborted(RuntimeError):
    """The run was stopped because its setup is wrong (e.g. skill inventory mismatch)."""


def launch_agent(prep: dict, ctx: AttemptContext | None, model: str, events_path: Path, stderr_path: Path,
                 timeout_s: float, cap: float | None, correct: bool) -> dict:
    """``run_agent_process`` for the campaign's runner (Claude Code adds a stream monitor
    that checks the init event's skill inventory and tracks API-equivalent cost)."""
    if ctx is not None and ctx.runner == "claude-code":
        def factory(path: Path) -> cc.StreamMonitor:
            return cc.StreamMonitor(path, model, g.claude_running_cost, on_init=ctx.check_inventory)

        return run_agent_process(prep["cmd"], prep["ws"], prep["env"], events_path, stderr_path, timeout_s, cap,
                                 model, correct, spool_dir=prep["scratch"], monitor_factory=factory)
    return run_agent_process(prep["cmd"], prep["ws"], prep["env"], events_path, stderr_path, timeout_s, cap,
                             model, correct, spool_dir=prep["scratch"])


def runner_fields(ctx: AttemptContext | None, events: list[dict], use: dict, proc: dict, scratch: Path) -> dict:
    """Claude Code extras for ``attempt.json``: API-equivalent cost, turns, the init-event
    inventory and its check, usage-limit flag. Writes the final answer to ``final.md``."""
    if ctx is None or ctx.runner != "claude-code":
        return {}
    res = g.claude_result(events) or {}
    final = attempt_artifact(scratch / "final.md", scratch)
    if res.get("result") and not final.exists():
        final.write_text(str(res["result"]))
    inv = proc.get("inventory") or cc.inventory_from_events(events)
    problems = proc.get("inventory_problems")
    if problems is None:
        problems = ctx.check_inventory(inv)
    return {
        "runner": "claude-code",
        "billing": "subscription",
        "cost_usd_equivalent": use.get("cost_usd_equivalent", use["cost_usd"]),
        "cost_source": use.get("cost_source"),
        "model_usage": use.get("model_usage"),
        "num_turns": res.get("num_turns"),
        "result_subtype": res.get("subtype"),
        "subagent_stats": {k: (res.get("subagent_stats") or {}).get(k) for k in ("spawned", "completed", "failed")},
        "inventory": {k: (inv or {}).get(k) for k in ("skills", "plugins", "mcp_servers", "model",
                                                      "claude_code_version", "memory_paths")},
        "inventory_problems": problems,
        "aborted": proc.get("aborted"),
    }


def keep_claude_session(scratch: Path, attempt_dir: Path) -> None:
    """Copy the Claude Code session transcript (``--keep-traces``), secrets redacted."""
    found = sorted((scratch / cc.CONFIG_DIR_NAME / "projects").glob("*/*.jsonl"))
    if found:
        shutil.copyfile(found[0], attempt_dir / "session.jsonl")
        san.redact_file(attempt_dir / "session.jsonl")


def run_attempt(case: Case, model: str, arm: str, attempt_dir: Path, skills_dir: Path,
                airflow_names: set[str], args: argparse.Namespace, budget: Budget) -> dict:
    """One agent run plus grading. Always returns (and writes) a record; usage and
    cost survive any exception after the agent ran (status ``harness_error``)."""
    ctx: AttemptContext | None = getattr(args, "ctx", None)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {"status": "harness_error", "reason": "", "primary_pass": False,
                              "primary_score": None, "secondary_score": None, "cost_usd": 0.0,
                              "cost_reported_usd": 0.0, "wall_s": 0.0, "launched": False}
    scratch = None
    env_lease = ExitStack()
    try:
        guard = (ctx.env_guards if ctx else {}).get(case.airflow_version)
        if guard is not None:
            env_lease.enter_context(guard.attempt())
        record["agent_env_pre"] = _guard_check(ctx, case.airflow_version)
        prep = prepare_agent(case.id, case.agent_env_py,
                             lambda d: make_workspace(case, [], d), case.prompt, model, case.max_turns,
                             skills_dir, args)
        scratch, ws, roots = prep["scratch"], prep["ws"], prep["roots"]
        record.update({"sandbox": bool(ctx and ctx.sandbox), "tmpdir": prep["env"]["TMPDIR"],
                       "agent_python": case.agent_env_py})
        events_path = attempt_dir / "events.jsonl"
        stderr_path = attempt_dir / "stderr.log"
        correct = g.cache_correction_applies(model, ctx.altimate_version if ctx else "")
        cap = attempt_cap(ctx, model, getattr(args, "max_run_cost_usd", None))
        record["launched"] = True
        proc = launch_agent(prep, ctx, model, events_path, stderr_path, case.timeout_s, cap, correct)
        record.update({"returncode": proc["returncode"], "wall_s": proc["wall_s"], "run_cap_usd": cap})
        events = g.load_events(events_path)
        use = g.usage(events, model, correct)
        budget.add(use["cost_usd"])
        record.update({
            "cost_usd": use["cost_usd"], "cost_reported_usd": use["cost_reported_usd"],
            "cost_list_price_usd": use["cost_list_price_usd"], "cost_correction_applied": correct,
            "double_counted_steps": use["double_counted_steps"], "tokens": use["tokens"], "steps": use["steps"],
        })
        record.update(runner_fields(ctx, events, use, proc, scratch))
        if proc.get("aborted"):
            raise AttemptAborted(proc["aborted"])
        record["agent_env_post"] = _guard_check(ctx, case.airflow_version, raise_on_fail=False)
        g.validate_workspace(ws)
        record["isolation"] = isolation_report(events, roots)
        record["isolation"]["escaping_symlinks"] = escaping_symlinks(ws)
        if record["isolation"]["escaping_symlinks"]:
            record["isolation"]["contamination_suspect"] = True
        record["contamination_suspect"] = record["isolation"]["contamination_suspect"]
        if record["contamination_suspect"]:
            log(f"CONTAMINATION SUSPECT {case.id} {slug(model)}: {record['isolation']['hits'][:3]} "
                f"{record['isolation']['escaping_symlinks'][:3]}")
        record["kill_command"] = bool(record["isolation"]["kill_commands"])
        if record["kill_command"]:
            log(f"BROAD KILL COMMAND {case.id} {slug(model)}: "
                f"{[k['command'][:80] for k in record['isolation']['kill_commands'][:3]]}")
        stderr = stderr_path.read_text(errors="replace")
        final = attempt_artifact(scratch / "final.md", scratch)
        if final.exists():
            san.write_text(attempt_dir / "final.md", final.read_text(errors="replace"))
        san.write_text(attempt_dir / "agent.patch", workspace_patch(ws, case.fixture, scratch))
        trace = next((e.get("path") for e in reversed(events) if e.get("type") == "trace_saved"), None)
        if trace:
            trace = str(attempt_artifact(trace, scratch))
        if trace and args.keep_traces and Path(trace).exists():
            shutil.copy2(trace, attempt_dir / "trace.json")
        skills_used = g.skill_invocations(events)
        auto = auto_loaded_skills(trace)
        record.update({
            "termination": {k: v for k, v in (g.termination(events) or {}).items()
                            if k in ("why_model_stopped", "why_harness_stopped", "done_reason")},
            "skill_invocations": skills_used,
            "auto_loaded_skills": auto,
            "airflow_skills_used": sorted({s["name"] for s in skills_used if s["name"] in airflow_names}
                                          | {a for a in auto if a in airflow_names}),
            "bash_commands": len(g.bash_commands(events)),
            "edited_files": len(g.edited_files(events)),
            "errors": g.error_messages(events)[-5:],
            "trace_path": trace if args.keep_traces else None,
        })
        # Infra failures are not graded (the attempt is retried).
        status, reason = classify_attempt(timed_out=proc["timed_out"], cost_capped=proc["cost_capped"],
                                          returncode=proc["returncode"], events=events, stderr=stderr,
                                          grade={"primary_pass": False, "checks": []}, grader_failed=False)
        grade = None
        if status != "infra_error":
            grade_ws = g.copy_workspace(ws, dest=scratch / "grade-ws")
            grade, grader_failed = run_grader(case, grade_ws, events_path, attempt_dir / "grade.json",
                                              attempt_dir / "grade.log")
            status, reason = classify_attempt(timed_out=proc["timed_out"], cost_capped=proc["cost_capped"],
                                              returncode=proc["returncode"], events=events, stderr=stderr,
                                              grade=grade, grader_failed=grader_failed)
        record.update({
            "status": status, "reason": reason,
            "primary_pass": bool(grade and grade.get("primary_pass")),
            "primary_score": grade.get("primary_score") if grade else None,
            "secondary_score": grade.get("secondary_score") if grade else None,
        })
    except g.UnsafeWorkspaceError as exc:
        record.update({"status": "task_fail", "reason": str(exc)[:500],
                       "primary_pass": False, "primary_score": 0.0, "contamination_suspect": True})
    except cc.TokenCommandError as exc:  # retried like any infra error; the retry re-runs the command
        record.update({"status": "infra_error", "reason": f"token command failed: {exc}"[:500]})
        log(f"TOKEN COMMAND FAILED in attempt {attempt_dir}: {exc}")
    except AttemptAborted as exc:
        record.update({"status": "harness_error", "reason": str(exc)[:500], "aborted": True})
        if ctx is not None:
            ctx.abort_reason = ctx.abort_reason or str(exc)
        log(f"ABORT in attempt {attempt_dir}: {exc}")
    except Exception as exc:  # noqa: BLE001 - keep usage/cost of a run that already happened
        import traceback

        record.update({"status": "harness_error", "reason": f"{type(exc).__name__}: {exc}"[:500],
                       "harness_exception": traceback.format_exc()[-2000:]})
        log(f"HARNESS EXCEPTION in attempt {attempt_dir}: {exc}")
        if scratch is not None:
            correct = g.cache_correction_applies(model, ctx.altimate_version if ctx else "")
            recover_usage(record, [attempt_dir / "events.jsonl", scratch / "events.jsonl"], model, correct)
            if record.get("usage_recovered_from"):
                budget.add(record["cost_usd"])
    finally:
        env_lease.close()
        if scratch is not None:
            if ctx is not None and ctx.runner == "claude-code":
                if args.keep_traces:
                    keep_claude_session(scratch, attempt_dir)
                if args.keep_workspaces:  # the kept config dir holds raw session transcripts
                    for f in (scratch / cc.CONFIG_DIR_NAME).rglob("*.jsonl"):
                        san.redact_file(f)
            if args.keep_workspaces:
                record["workspace"] = str(scratch / "ws")
            else:
                shutil.rmtree(scratch, ignore_errors=True)
        san.write_json(attempt_dir / "attempt.json", record)
    return record


def new_row(case: Case, model: str, run_idx: int, arm: str) -> dict:
    return {"case": case.id, "area": case.area, "split": case.split, "airflow_version": case.airflow_version,
            "arm": arm, "model": model, "run": run_idx, "attempts": []}


def finalize_row(row: dict) -> dict:
    """Row summary from its attempts. Cost sums every attempt, including failed ones."""
    attempts = row["attempts"]
    final = attempts[-1] if attempts else {"status": "harness_error", "reason": "no attempt recorded"}
    row.update({
        "status": final["status"],
        "primary_pass": bool(final.get("primary_pass")),
        "primary_score": final.get("primary_score"),
        "secondary_score": final.get("secondary_score"),
        "cost_usd": round(sum(a.get("cost_usd") or 0 for a in attempts), 6),
        "cost_reported_usd": round(sum(a.get("cost_reported_usd") or 0 for a in attempts), 6),
        "tokens": final.get("tokens"),
        "wall_s": final.get("wall_s"),
        "steps": final.get("steps"),
        "airflow_skills_used": final.get("airflow_skills_used", []),
        "skill_invocations": final.get("skill_invocations", []),
        "contamination_suspect": any(a.get("contamination_suspect") for a in attempts),
        "kill_command": any(a.get("kill_command") for a in attempts),
        "killed_attempts": sum(1 for a in attempts if is_killed(a)),
        "agent_env_restored": any((a.get(k) or {}).get("restored") for a in attempts
                                  for k in ("agent_env_pre", "agent_env_post")),
        "agent_env_restore_failed": any((a.get(k) or {}).get("changed") and not (a.get(k) or {}).get("restored")
                                        for a in attempts for k in ("agent_env_pre", "agent_env_post")),
        "retries": max(0, sum(1 for a in attempts if not str(a.get("status")).startswith("skipped_")) - 1),
    })
    if any("cost_usd_equivalent" in a for a in attempts):
        row.update({
            "cost_usd_equivalent": round(sum(a.get("cost_usd_equivalent") or 0 for a in attempts), 6),
            "num_turns": final.get("num_turns"),
            "usage_limit_attempts": sum(1 for a in attempts if a.get("usage_limit")),
        })
    return row


def run_one(case: Case, model: str, run_idx: int, arm: str, out_dir: Path, skills_dir: Path,
            airflow_names: set[str], args: argparse.Namespace, budget: Budget, row: dict | None = None) -> dict:
    """Attempts for one run; ``row`` (from :func:`new_row`) is filled in place so a caller
    that catches an exception still has every attempt and its cost."""
    row = row if row is not None else new_row(case, model, run_idx, arm)
    run_dir = out_dir / "runs" / case.id / slug(model) / f"run-{run_idx}"
    label = f"{case.id} {slug(model)} run-{run_idx}"
    attempt_loop(row, lambda k: run_attempt(case, model, arm, run_dir / f"attempt-{k}", skills_dir, airflow_names,
                                            args, budget),
                 getattr(args, "ctx", None), budget, label, next_attempt_index(run_dir))
    return finalize_row(row)


def next_attempt_index(run_dir: Path) -> int:
    """First unused ``attempt-K`` index (a resumed run keeps its earlier attempt dirs)."""
    used = [int(m.group(1)) for p in (run_dir.iterdir() if run_dir.is_dir() else [])
            if (m := re.fullmatch(r"attempt-(\d+)", p.name))]
    return max(used) + 1 if used else 0


def attempt_loop(row: dict, launch, ctx: AttemptContext | None, budget: Budget, label: str,
                 first: int = 0, sleep=time.sleep) -> None:
    """Attempts for one run, appended to ``row["attempts"]``.

    - Budget exhausted before launch: ``skipped_budget``.
    - Retryable ``infra_error``: altimate-code retries twice (20 s, 40 s); claude-code
      three times with exponential backoff (30, 60, 120 s). A run killed from outside
      (signal the harness did not send) is retried at most twice on either runner.
    - claude-code usage (plan) limit: the campaign-wide :class:`claude_code.UsageLimitGate`
      pauses every worker with backoff (not counted as a retry) for up to 30 min,
      then stops; unlaunched runs get ``skipped_usage_limit`` (rerun with ``--resume``).
    - A setup abort (inventory mismatch): later runs get ``skipped_abort``.
    """
    claude = ctx is not None and ctx.runner == "claude-code"
    max_retries = cc.MAX_INFRA_RETRIES if claude else MAX_INFRA_RETRIES
    gate = ctx.usage_gate if claude else None
    attempt, retries = first, 0
    while True:
        if gate is not None and not gate.wait():
            row["attempts"].append({"status": "skipped_usage_limit", "reason": "campaign stopped by usage limit",
                                    "cost_usd": 0.0, "launched": False})
            return
        # checked after a usage-limit pause: another worker may have aborted or spent the budget
        if ctx is not None and ctx.abort_reason:
            row["attempts"].append({"status": "skipped_abort", "reason": f"campaign aborted: {ctx.abort_reason}"[:500],
                                    "cost_usd": 0.0, "launched": False})
            return
        if not budget.can_launch():
            row["attempts"].append({"status": "skipped_budget", "reason": "campaign budget exhausted",
                                    "cost_usd": 0.0, "launched": False})
            return
        rec = launch(attempt)
        rec["attempt"] = attempt
        row["attempts"].append(rec)
        log(f"{label} attempt-{attempt}: {rec['status']} (${rec.get('cost_usd') or 0:.2f}, {rec.get('wall_s')}s) "
            f"{str(rec.get('reason'))[:100]}")
        attempt += 1
        if gate is not None and cc.is_usage_limit(rec):
            rec["usage_limit"] = True
            gate.report_limit(str(rec.get("reason") or ""))
            continue  # gate.wait() pauses, or returns False once the gate stops
        if gate is not None and rec.get("status") != "infra_error":
            gate.report_ok()
        killed = is_killed(rec)
        if killed:
            rec["killed"] = True
        if not should_retry(rec) or retries >= (MAX_KILLED_RETRIES if killed else max_retries):
            return
        retries += 1
        wait = cc.infra_backoff_s(retries) if claude else 20 * retries
        log(f"retry {retries} for {label} after infra_error (sleep {wait}s)")
        sleep(wait)


def run_jobs(cases: list[Case], models: list[str], runs: int, run_offset: int = 0) -> list[tuple[Case, str, int]]:
    """(case, model, run index) jobs; indices are ``run_offset+1 .. run_offset+runs``, run-major."""
    return [(c, m, i) for i in range(run_offset + 1, run_offset + runs + 1) for c in cases for m in models]


def slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------


def env_versions(versions: set[str]) -> dict:
    out = {}
    for v in sorted(versions):
        py = g.env_python(v)
        if not Path(py).exists():
            out[v] = {"error": f"missing {py}; run evals/harness/setup_envs.sh"}
            continue
        code = ("import sys, airflow, importlib.metadata as m; print(sys.version.split()[0], airflow.__version__, "
                "m.version('pytest'), m.version('duckdb'), m.version('pandas'))")
        res = g.run_cmd([py, "-c", code], env={**g.scrubbed_environ(), "PYTHONWARNINGS": "ignore",
                                                "AIRFLOW_HOME": tempfile.mkdtemp(prefix="eval-ver-")}, timeout=120)
        ruff = g.run_cmd([str(Path(py).parent / "ruff"), "--version"], timeout=30)
        parts = (res.stdout.strip().splitlines() or [""])[-1].split()
        keys = ("python", "airflow", "pytest", "duckdb", "pandas")
        out[v] = dict(zip(keys, parts)) if len(parts) == len(keys) else {"error": res.tail(5)}
        out[v]["ruff"] = ruff.stdout.strip().replace("ruff ", "")
        out[v]["python_path"] = py
    return out


def repo_head() -> str | None:
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True)
    return res.stdout.strip() or None


def altimate_version() -> str:
    res = subprocess.run(["altimate-code", "--version"], capture_output=True, text=True, timeout=60)
    return res.stdout.strip()


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------


def selftest_variants(case: Case) -> list[tuple[str, list[Path], bool]]:
    """(label, overlays on top of fixture, expected primary_pass)."""
    variants = [("reference", [case.reference], True)]
    if case.alt_reference:
        variants.append(("alt_reference", [case.alt_reference], True))
    variants.append(("fixture", [], False))
    for m in case.mutants:
        variants.append((f"mutant:{m.name}", [case.reference, m], False))
    return variants


def self_test(cases: list[Case], parallel: int, out: Path | None) -> int:
    root = Path(tempfile.mkdtemp(prefix="selftest-", dir=work_root()))
    empty_events = root / "empty-events.jsonl"
    empty_events.write_text("")
    jobs = [(c, label, ovs, exp) for c in cases for (label, ovs, exp) in selftest_variants(c)]

    def job(item):
        case, label, overlays, expected = item
        d = root / case.id / label.replace(":", "_")
        d.mkdir(parents=True)
        ws = make_workspace(case, overlays, d)
        t0 = time.time()
        grade, failed = run_grader(case, ws, empty_events, d / "grade.json", d / "grade.log")
        return {
            "case": case.id, "variant": label, "expected_pass": expected,
            "primary_pass": None if failed else grade["primary_pass"],
            "primary_score": None if failed else grade["primary_score"],
            "failed_primary": [] if failed else [c["name"] for c in grade["checks"]
                                                 if c["kind"] == "primary" and not c["passed"]],
            "grader_error": failed, "grade_log": str(d / "grade.log"), "seconds": round(time.time() - t0, 1),
        }

    with cf.ThreadPoolExecutor(max_workers=max(1, parallel)) as ex:
        rows = list(ex.map(job, jobs))
    violations = 0
    print(f"\n{'case':28} {'variant':28} {'expect':7} {'got':7} {'score':6} {'s':>5}  verdict / failing primary checks")
    for r in rows:
        ok = (not r["grader_error"]) and r["primary_pass"] == r["expected_pass"]
        if not r["expected_pass"] and not r["grader_error"] and not r["failed_primary"]:
            ok = False
        violations += 0 if ok else 1
        got = "ERROR" if r["grader_error"] else ("pass" if r["primary_pass"] else "fail")
        score = "-" if r["primary_score"] is None else f"{r['primary_score']:.2f}"
        why = "OK" if ok else "VIOLATION"
        if r["grader_error"]:
            why += f" grader error, see {r['grade_log']}"
        elif r["failed_primary"]:
            why += " | " + ", ".join(r["failed_primary"])[:120]
        print(f"{r['case']:28} {r['variant']:28} {'pass' if r['expected_pass'] else 'fail':7} {got:7} {score:6} "
              f"{r['seconds']:5.0f}  {why}")
    print(f"\nself-test: {len(rows)} variants, {violations} violation(s); artifacts in {root}")
    if out:
        out.mkdir(parents=True, exist_ok=True)
        san.write_json(out / "selftest.json", rows)
    return 1 if violations else 0


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def default_models(runner: str) -> tuple[str, ...]:
    return cc.DEFAULT_MODELS if runner == "claude-code" else DEFAULT_MODELS


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", type=Path, default=REPO_ROOT / "evals/airflow/cases")
    ap.add_argument("--arm", choices=ARMS)
    ap.add_argument("--runner", choices=RUNNERS, default="altimate-code",
                    help="agent CLI: altimate-code (default) or claude-code (needs CLAUDE_CODE_OAUTH_TOKEN or EVAL_CLAUDE_TOKEN_CMD)")
    ap.add_argument("--models", default=None,
                    help="comma-separated model ids (altimate-code: provider/model; claude-code: e.g. "
                         "claude-sonnet-5-5); default: the runner's three default models")
    ap.add_argument("--resume", action="store_true",
                    help="keep finished runs in --out/runs.jsonl and launch only missing or unscored ones "
                         f"({', '.join(RESUMABLE_STATUSES)})")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--run-offset", type=int, default=0,
                    help="first run index is OFFSET+1, so a later campaign can add runs to an earlier one "
                         "without colliding (e.g. --runs 1 --run-offset 2 runs only run-3)")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--split", choices=("dev", "holdout", "all"), default="dev")
    ap.add_argument("--case", action="append", dest="case_ids", help="run only this case id (repeatable)")
    ap.add_argument("--out", type=Path, help="result directory (evals/airflow/results/<run-name>/)")
    ap.add_argument("--skills-dir", type=Path, default=REPO_ROOT / "skills/airflow")
    ap.add_argument("--repo-skills-dir", type=Path, default=REPO_ROOT / "skills",
                    help="existing repo skills loaded in BOTH arms (its airflow/ subdir is excluded)")
    ap.add_argument("--max-cost-usd", type=float, default=60.0, help="campaign budget cap")
    ap.add_argument("--max-run-cost-usd", type=float, default=None,
                    help="per-run cost cap for every model (0 = none); default: per-model DEFAULT_RUN_CAP_USD")
    ap.add_argument("--max-run-cost-usd-by-model", default="",
                    help="per-run caps as MODEL=USD,... (full id or key like claude-opus-5-5); wins over "
                         "--max-run-cost-usd")
    ap.add_argument("--no-sandbox", action="store_true",
                    help="do not wrap agents in sandbox-exec (contamination detection still runs)")
    ap.add_argument("--self-test", action="store_true", help="grader self-test only (no LLM)")
    ap.add_argument("--inventory-only", action="store_true", help="stage skills, verify inventory, exit")
    ap.add_argument("--keep-workspaces", action="store_true")
    ap.add_argument("--keep-traces", action="store_true", help="copy altimate-code traces into results")
    args = ap.parse_args(argv)
    for name in ("cases", "out", "skills_dir", "repo_skills_dir"):
        if getattr(args, name) is not None:
            setattr(args, name, getattr(args, name).resolve())
    if not args.self_test and not args.arm:
        ap.error("--arm is required unless --self-test")
    if not args.self_test and not args.inventory_only and not args.out:
        ap.error("--out is required")
    if args.runs < 1 or args.run_offset < 0:
        ap.error("--runs must be >= 1 and --run-offset >= 0")
    if args.models is None:
        args.models = ",".join(default_models(args.runner))
    try:
        args.run_cap_overrides = parse_cap_map(args.max_run_cost_usd_by_model)
    except ValueError as exc:
        ap.error(str(exc))
    return args


def missing_interpreters(versions: set[str], agent: bool = True) -> list[str]:
    """Grader (and agent) env interpreters that do not exist, as messages."""
    missing = []
    for v in sorted(versions):
        pys = [("grader", g.env_python(v))] + ([("agent", g.agent_env_python(v))] if agent else [])
        for kind, py in pys:
            if not Path(py).exists():
                missing.append(f"{kind} env for airflow {v}: {py}")
    return missing


def make_env_guards(versions: set[str]) -> dict[str, iso.AgentEnvGuard]:
    """One guard per agent env, checked (and restored if dirty) before the campaign starts."""
    guards = {}
    for v in sorted(versions):
        guard = iso.AgentEnvGuard(Path(g.agent_env_python(v)).parent.parent)
        res = guard.check()
        if res["changed"]:
            log(f"agent env {guard.venv.name} differed from its pristine fingerprint before the campaign: "
                f"restored={res['restored']} {res['detail']}")
            if not res["restored"]:
                raise SystemExit(f"agent env {guard.venv} is dirty and could not be restored; "
                                 "re-run evals/harness/setup_envs.sh")
        guards[v] = guard
    return guards


def require_claude_token() -> None:
    """claude-code runs authenticate only through an OAuth token (the per-attempt config
    dir has no stored login): :data:`claude_code.TOKEN_VAR` in the environment, or
    :data:`claude_code.TOKEN_CMD_VAR`, which is run once here to fail fast and again
    before every attempt. The token is never printed."""
    if os.environ.get(cc.TOKEN_CMD_VAR, "").strip():
        try:
            cc.fetch_token(os.environ[cc.TOKEN_CMD_VAR])
        except cc.TokenCommandError as exc:
            raise SystemExit(f"--runner claude-code: {exc}") from None
        return
    if not os.environ.get(cc.TOKEN_VAR):
        raise SystemExit(f"--runner claude-code needs {cc.TOKEN_VAR} in the environment, or "
                         f"{cc.TOKEN_CMD_VAR} set to a command that prints a token")


def claude_inventory(probe: Path, staged: Path, flat: Path, agent_py: str, model: str, sandbox: bool,
                     out_dir: Path | None) -> dict:
    """Skill inventory under the exact claude-code agent env, from a local ``/context``
    run (no model call): the init event plus each skill's source and any memory files."""
    ws = probe / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    git(ws, "init", "-q")
    config_dir, mcp = cc.prepare_config_dir(probe, flat)
    env = cc.agent_env(build_agent_env(probe, ws, staged, agent_py), config_dir)
    cmd = cc.inventory_command(model, mcp)
    if sandbox:
        roots = IsolationRoots(scratch=probe, agent_venv=Path(agent_py).parent.parent, staged_skills=staged,
                               out_dir=out_dir, work_root=work_root(), runner="claude-code")
        (probe / "sandbox.sb").write_text(roots.sandbox_profile())
        cmd = iso.sandbox_wrap(cmd, probe / "sandbox.sb")
    res = subprocess.run(cmd, cwd=ws, env=env, capture_output=True, text=True, timeout=300,
                         stdin=subprocess.DEVNULL)
    events = [e for e in (_json_line(x) for x in res.stdout.splitlines()) if e]
    inv = cc.inventory_from_events(events, with_context=True)
    if res.returncode != 0 or inv is None:
        raise RuntimeError(f"claude /context inventory failed rc={res.returncode}: "
                           f"{san.redact_secrets(res.stderr[-800:] or res.stdout[-800:])}")
    inv["ancestor_memory_files_disabled"] = cc.ancestor_memory_files(ws)
    inv["sandbox"] = sandbox
    return inv


def _json_line(line: str) -> dict | None:
    try:
        e = json.loads(line)
    except ValueError:
        return None
    return e if isinstance(e, dict) else None


def run_key(row: dict) -> tuple:
    return (row.get("case"), row.get("model"), row.get("run"))


def load_resume(rows_path: Path, key=run_key) -> tuple[dict[tuple, dict], dict[tuple, dict]]:
    """``(done, redo)`` rows of an earlier campaign by (case, model, run).

    ``done``: final status is scored (ok, task_fail, timeout, ...), kept as is.
    ``redo``: unscored (:data:`RESUMABLE_STATUSES`); run again, carrying the earlier
    attempts (and their spend) into the new row. A later row for the same run wins.
    """
    done: dict[tuple, dict] = {}
    redo: dict[tuple, dict] = {}
    if not rows_path.exists():
        return done, redo
    for line in rows_path.read_text().splitlines():
        row = _json_line(line) if line.strip() else None
        if not row:
            continue
        k = key(row)
        done.pop(k, None)
        redo.pop(k, None)
        (redo if row.get("status") in RESUMABLE_STATUSES else done)[k] = row
    return done, redo


def compact_rows(rows_path: Path, key=run_key) -> None:
    """Keep only the last row per run in ``runs.jsonl``.

    A resumed campaign first re-writes its unscored rows (so an interruption keeps
    their attempts and spend), then appends each rerun's row, which carries those
    attempts; compaction drops the superseded copies so ``report.py`` sees one row per run.
    """
    if not rows_path.exists():
        return
    last: dict[tuple, str] = {}
    for line in rows_path.read_text().splitlines():
        row = _json_line(line) if line.strip() else None
        if row:
            k = key(row)
            last.pop(k, None)  # re-insert: order follows the latest row
            last[k] = line
    rows_path.write_text("".join(v + "\n" for v in last.values()))


def resume_meta_problems(meta: dict, args: argparse.Namespace, models: list[str],
                         case_hashes: dict[str, str] | None = None, skills_sha: str | None = None) -> list[str]:
    """Settings that must match the campaign being resumed.

    Besides arm, runner and models, the case content hashes and the ``skills/airflow`` hash must match what
    ``meta.json`` recorded, because the finished rows are kept and meta.json is rewritten with the current
    hashes: resuming after a grader or skill change would relabel old runs as current. Start a new ``--out``
    dir instead (``report.py`` merges dirs and flags mixed revisions).
    """
    problems = []
    for key, now in (("arm", args.arm), ("runner", args.runner), ("models", models)):
        before = meta.get(key, "altimate-code" if key == "runner" else None)
        if before != now:
            problems.append(f"{key}: was {before!r}, now {now!r}")
    old_cases = meta.get("cases") or {}
    for cid, sha in sorted((case_hashes or {}).items()):
        before = (old_cases.get(cid) or {}).get("sha256")
        if before and before != sha:
            problems.append(f"case {cid} changed since the campaign started")
    if skills_sha and meta.get("airflow_skills_sha256") and meta["airflow_skills_sha256"] != skills_sha:
        problems.append("skills/airflow changed since the campaign started")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cases = discover_cases(args.cases, args.split, args.case_ids)
    if args.self_test:
        if not cases:
            print("no cases selected", file=sys.stderr)
            return 1
        missing = missing_interpreters({c.airflow_version for c in cases}, agent=False)
        if missing:
            raise SystemExit("missing interpreters (run evals/harness/setup_envs.sh):\n  " + "\n  ".join(missing))
        return self_test(cases, args.parallel, args.out)

    versions = {c.airflow_version for c in cases} or {"3.3"}
    missing = missing_interpreters(versions)
    if missing:
        raise SystemExit("missing interpreters (run evals/harness/setup_envs.sh):\n  " + "\n  ".join(missing))
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    claude = args.runner == "claude-code"
    if claude:
        require_claude_token()
    run_name = args.out.name if args.out else f"inventory-{args.arm}"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    args.work_dir = work_root() / f"{run_name}-{args.arm}-{stamp}"
    args.work_dir.mkdir(parents=True)
    staged = stage_skills(args.arm, args.repo_skills_dir, args.skills_dir, args.work_dir / "skills")
    airflow_names = skill_names(args.skills_dir) if args.skills_dir.exists() else []
    repo_names = [n for n in skill_names(staged) if n not in airflow_names]
    sandbox = not args.no_sandbox and iso.sandbox_available()

    # Inventory under the exact agent environment.
    probe = args.work_dir / "inventory-probe"
    flat = None
    if claude:
        flat = args.work_dir / "skills-flat"
        repo_names = [n for n in cc.flatten_skills(staged, flat) if n not in airflow_names]
        inventory = claude_inventory(probe, staged, flat, g.agent_env_python(sorted(versions)[0]), models[0],
                                     sandbox, args.out)
        problems = cc.check_inventory(args.arm, inventory, airflow_names, repo_names)
        inv_summary = sorted((s.get("name"), s.get("source")) for s in inventory.get("context_skills") or [])
        n_skills = len(inventory.get("skills") or [])
    else:
        probe.mkdir()
        (probe / "ws").mkdir()
        git(probe / "ws", "init", "-q")
        inv_env = build_agent_env(probe, probe / "ws", staged, g.agent_env_python(sorted(versions)[0]))
        inventory = list_skills(inv_env, probe / "ws")
        problems = check_inventory(args.arm, inventory, staged, airflow_names, repo_names)
        inv_summary = sorted((s.get("name"), s.get("source")) for s in inventory)
        n_skills = len(inventory)
    log(f"inventory ({args.runner}, {args.arm}): {n_skills} skills; airflow skills expected={airflow_names}; "
        f"problems={problems or 'none'}")
    if args.inventory_only:
        if claude:
            print(san.dumps({"arm": args.arm, "runner": args.runner, "problems": problems, "inventory": inventory}))
        else:
            print(san.dumps({"arm": args.arm, "staged_skills_dir": str(staged), "problems": problems,
                             "skills": [{"name": s.get("name"), "source": s.get("source"),
                                         "location": s.get("location")} for s in inventory]}))
        return 1 if problems else 0
    if problems:
        log("ABORT: skill inventory check failed")
        return 2
    if not cases:
        log("no cases selected")
        return 1

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    rows_path = out / "runs.jsonl"
    done: dict[tuple, dict] = {}
    redo: dict[tuple, dict] = {}
    old_meta: dict = {}
    if args.resume and rows_path.exists():
        old_meta = json.loads((out / "meta.json").read_text()) if (out / "meta.json").exists() else {}
        resume_problems = resume_meta_problems(
            old_meta, args, models, {c.id: hash_dir(c.dir) for c in cases},
            hash_dir(args.skills_dir) if args.arm == "skill" else None)
        if resume_problems:
            log(f"ABORT: --resume settings differ from {out}/meta.json: {resume_problems}")
            return 2
        done, redo = load_resume(rows_path)
    if not args.no_sandbox and not sandbox:
        log("sandbox-exec unavailable: running without a sandbox (contamination detection only)")
    ctx = AttemptContext(
        out_dir=out, work_dir=args.work_dir, staged_skills=staged,
        altimate_version="" if claude else altimate_version(),
        sandbox=sandbox, env_guards=make_env_guards(versions),
        run_caps={m: run_cap_for(m, args.run_cap_overrides, args.max_run_cost_usd) for m in models},
        runner=args.runner, flat_skills=flat, arm=args.arm, airflow_names=airflow_names, repo_names=repo_names,
        runner_version=cc.version() if claude else "",
        usage_gate=cc.UsageLimitGate(log=log) if claude else None,
        expected_skills=list(inventory.get("skills") or []) if claude else None,
    )
    args.ctx = ctx
    san.write_json(out / f"inventory-{args.arm}.json", inventory)
    meta = {
        "run_name": run_name,
        "arm": args.arm,
        "runner": args.runner,
        "models": models,
        "runs_per_case": args.runs,
        "run_offset": args.run_offset,
        "run_indices": list(range(args.run_offset + 1, args.run_offset + args.runs + 1)),
        "split": args.split,
        "argv": sys.argv,
        "started_at": old_meta.get("started_at") or utcnow(),
        "altimate_code_version": ctx.altimate_version or None,
        "small_model": None if claude else SMALL_MODEL,
        "envs": env_versions(versions),
        "agent_envs": {v: {"python": g.agent_env_python(v), "pristine_fingerprint": gd.pristine}
                       for v, gd in ctx.env_guards.items()},
        "isolation": {"sandbox": sandbox, "per_attempt_tmpdir": True, "per_attempt_xdg_data": True,
                      "pip_require_virtualenv": True, "signals_same_sandbox_only": sandbox},
        "cost_correction": {m: g.cache_correction_applies(m, ctx.altimate_version) for m in models},
        "cases": {c.id: {"sha256": hash_dir(c.dir), "area": c.area, "split": c.split,
                         "airflow_version": c.airflow_version, "timeout_s": c.timeout_s,
                         "max_turns": c.max_turns} for c in cases},
        "staged_skills_sha256": hash_dir(staged),
        "airflow_skills_dir": str(args.skills_dir),
        "airflow_skills_sha256": hash_dir(args.skills_dir) if args.arm == "skill" else None,
        # Always recorded, including for the baseline arm (which does not load these skills).
        "airflow_skills_dir_sha256": hash_dir(args.skills_dir),
        "airflow_skill_names": airflow_names,
        "repo_skill_names": repo_names,
        "inventory": inv_summary,
        "harness_sha256": hash_dir(HARNESS_DIR),
        "repo_head": repo_head(),
        "host": {"platform": platform.platform(), "python": platform.python_version()},
        "budget": {"cap_usd": args.max_cost_usd, "per_run_cap_usd": ctx.run_caps},
    }
    if claude:
        meta.update({
            "claude_code_version": ctx.runner_version,
            "billing": "subscription (Claude Code OAuth); cost_usd = cost_usd_equivalent = API-equivalent "
                       "total_cost_usd reported by Claude Code",
        })
        meta["isolation"].update({
            "claude_config_dir": "fresh per attempt (<scratch>/claude-config, skills in skills/<name>/)",
            "claude_env": cc.ISOLATION_ENV, "strict_mcp_config": True,
            "ancestor_memory_files_disabled": inventory.get("ancestor_memory_files_disabled"),
        })
    if args.resume:
        meta["resumed_at"] = list(old_meta.get("resumed_at") or []) + ([utcnow()] if old_meta else [])
        meta["resume"] = {"kept_runs": len(done), "rerun_runs": len(redo)}
    san.write_json(out / "meta.json", meta)
    budget = Budget(args.max_cost_usd)
    budget.spent = sum(float(r.get("cost_usd") or 0) for r in [*done.values(), *redo.values()])
    jobs = [j for j in run_jobs(cases, models, args.runs, args.run_offset) if (j[0].id, j[1], j[2]) not in done]
    log(f"{len(jobs)} runs ({len(cases)} cases x {len(models)} models x {args.runs}, "
        f"run indices {args.run_offset + 1}..{args.run_offset + args.runs}; {len(done)} already done) "
        f"runner={args.runner} arm={args.arm} parallel={args.parallel} sandbox={sandbox} caps={ctx.run_caps} "
        f"work={args.work_dir}")
    lock = threading.Lock()
    rows = list(done.values())

    def job(item):
        case, model, idx = item
        row = new_row(case, model, idx, args.arm)
        prev = redo.get((case.id, model, idx))
        if prev:  # keep the earlier attempts (and their spend) of a resumed run
            row["attempts"] = [a for a in prev.get("attempts") or [] if not str(a.get("status")).startswith("skipped_")]
        try:
            row = run_one(case, model, idx, args.arm, out, staged, set(airflow_names), args, budget, row)
        except Exception as exc:  # noqa: BLE001 - keep every run accounted for, with its spend
            import traceback

            row["attempts"].append({"status": "harness_error", "reason": f"{type(exc).__name__}: {exc}"[:500],
                                    "cost_usd": 0.0, "launched": False})
            finalize_row(row)
            row["harness_exception"] = traceback.format_exc()[-2000:]
            log(f"HARNESS EXCEPTION {case.id} {model} run-{idx}: {exc}")
        with lock:
            rows.append(row)
            san.append_jsonl(rows_path, row)
        return row

    if rows_path.exists():
        rows_path.rename(rows_path.with_suffix(f".jsonl.prev-{stamp}"))
    for row in [*done.values(), *redo.values()]:
        san.append_jsonl(rows_path, row)
    try:
        with cf.ThreadPoolExecutor(max_workers=max(1, args.parallel)) as ex:
            list(ex.map(job, jobs))
    finally:
        if args.resume:
            compact_rows(rows_path)
    meta["finished_at"] = utcnow()
    meta["budget"].update({"spent_usd": round(budget.spent, 4), "stopped_early": budget.stopped})
    meta["status_counts"] = {s: sum(1 for r in rows if r["status"] == s) for s in sorted({r["status"] for r in rows})}
    meta["isolation"].update({
        "contamination_suspect_runs": sum(1 for r in rows if r.get("contamination_suspect")),
        "kill_command_runs": sum(1 for r in rows if r.get("kill_command")),
        "killed_attempts": sum(r.get("killed_attempts") or 0 for r in rows),
        "agent_env_restores": {v: gd.restores for v, gd in ctx.env_guards.items()},
    })
    rc = 0
    if ctx.usage_gate is not None:
        meta["usage_limit"] = {"stopped": ctx.usage_gate.stopped, "paused_s": ctx.usage_gate.waited_s,
                               "events": ctx.usage_gate.events}
        if ctx.usage_gate.stopped:
            rc = 3
            log("STOPPED by usage limit; rerun the same command with --resume to continue")
    if ctx.abort_reason:
        meta["aborted"] = ctx.abort_reason
        rc = 2
        log(f"ABORTED: {ctx.abort_reason}")
    san.write_json(out / "meta.json", meta)
    passed = sum(1 for r in rows if r.get("primary_pass"))
    log(f"done: {passed}/{len(rows)} primary pass; spent ${budget.spent:.2f}"
        f"{' (API-equivalent, subscription)' if claude else ''}; "
        f"contamination suspects={meta['isolation']['contamination_suspect_runs']}; results in {out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
