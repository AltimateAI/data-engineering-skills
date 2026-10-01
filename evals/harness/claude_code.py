"""Claude Code runner for the eval harness (``--runner claude-code``). Standard library only.

Each attempt runs ``claude -p ... --output-format stream-json --verbose`` with:

- a fresh ``CLAUDE_CONFIG_DIR`` inside the attempt scratch dir, so the user's
  ``~/.claude`` settings, CLAUDE.md, hooks, plugins, MCP servers, skills and
  sessions never load. The arm's skills are staged flat into
  ``$CLAUDE_CONFIG_DIR/skills/<name>/`` (Claude Code's personal-skills location;
  verified with 2.1.286: they are listed with source "User").
- ``--strict-mcp-config`` with an empty MCP config.
- :data:`ISOLATION_ENV`: no CLAUDE.md / AGENTS.md discovery (Claude Code otherwise
  loads ``~/.claude/CLAUDE.md`` as an ancestor of any workspace under ``~``), no
  auto-memory, telemetry, error reporting, surveys or updates, and Claude Code's
  own temp files (messaging socket, cwd tracking) under the attempt's ``TMPDIR``.
- inherited ``CLAUDE*`` / ``ANTHROPIC*`` variables removed (this harness may itself
  run inside a Claude Code session), except :data:`TOKEN_VAR`, which carries the
  user's subscription OAuth token. The harness never prints or writes it;
  ``sanitize.py`` redacts ``sk-ant-*`` patterns in every artifact. With
  :data:`TOKEN_CMD_VAR` set, the token is instead fetched from that command right
  before each attempt (:func:`with_fresh_token`) and passed to that attempt only.

The skill inventory comes from the stream's ``system/init`` event (``skills``,
``plugins``, ``mcp_servers``) and, before a campaign, from a local ``/context``
command, which makes no model call and also reports each skill's source and any
loaded memory files.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

CLAUDE_BIN = os.environ.get("EVAL_CLAUDE_BIN", "claude")
DEFAULT_MODELS = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1")
TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
#: Optional command (split with :func:`shlex.split`, no shell) that prints a current
#: OAuth token on stdout. Run before each attempt, so long campaigns survive token
#: expiry and an auth-failure retry gets a fresh token.
TOKEN_CMD_VAR = "EVAL_CLAUDE_TOKEN_CMD"
TOKEN_CMD_TIMEOUT_S = 180
ENV_SCRUB_PREFIXES = ("CLAUDE", "ANTHROPIC")
ISOLATION_ENV = {
    "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY": "1",
    "CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL": "1",
    "CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL": "1",
    "DISABLE_AUTOUPDATER": "1",
    "DISABLE_UPDATES": "1",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "DISABLE_BUG_COMMAND": "1",
    "DISABLE_FEEDBACK_COMMAND": "1",
}
CONFIG_DIR_NAME = "claude-config"
MCP_CONFIG_NAME = "mcp-empty.json"
#: Retries after an infra error (rate limit, overload, auth), with exponential backoff.
MAX_INFRA_RETRIES = 3
INFRA_BACKOFF_S = 30
#: A plan usage limit pauses the campaign with backoff for at most this long in total,
#: then stops it cleanly (rerun with --resume to continue).
USAGE_LIMIT_MAX_WAIT_S = 30 * 60
USAGE_LIMIT_FIRST_WAIT_S = 120
USAGE_LIMIT = re.compile(
    r"usage limit|hit your (?:usage )?limit|reached your (?:usage )?limit|out of extra usage|"
    r"requires usage credits|rate_limit_event rejected", re.I)
#: Memory files and project-level config that must not exist above a workspace.
ANCESTOR_MEMORY_FILES = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", ".claude/CLAUDE.md", ".claude/rules")


# --------------------------------------------------------------------------
# Skills, config dir, env, command
# --------------------------------------------------------------------------


def _skill_name(md: Path) -> str:
    m = re.match(r"^---\s*\n(.*?)\n---", md.read_text(errors="replace"), re.S)
    found = re.search(r"^name:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", m.group(1), re.M) if m else None
    return found.group(1).strip() if found else md.parent.name


def flatten_skills(staged: Path, dest: Path) -> list[str]:
    """Copy every skill dir (one with a SKILL.md) under ``staged`` to ``dest/<name>/``.

    Claude Code only discovers ``skills/<name>/SKILL.md`` one level deep, while
    the repo groups skills (``dbt/creating-dbt-models``). Dirs whose name starts
    with ``_`` or ``.`` (``airflow/_shared``) are never skills. Raises on duplicate names.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    names: list[str] = []
    for md in sorted(staged.rglob("SKILL.md")):
        rel = md.parent.relative_to(staged)
        if any(p.startswith(("_", ".")) for p in rel.parts):
            continue
        name = _skill_name(md)
        if name in names:
            raise ValueError(f"duplicate skill name {name!r} under {staged}")
        names.append(name)
        shutil.copytree(md.parent, dest / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    return names


def prepare_config_dir(scratch: Path, flat_skills: Path) -> tuple[Path, Path]:
    """Fresh ``CLAUDE_CONFIG_DIR`` with the arm's skills, plus an empty MCP config."""
    cfg = scratch / CONFIG_DIR_NAME
    if cfg.exists():
        shutil.rmtree(cfg)
    cfg.mkdir(parents=True)
    shutil.copytree(flat_skills, cfg / "skills")
    mcp = scratch / MCP_CONFIG_NAME
    mcp.write_text(json.dumps({"mcpServers": {}}))
    return cfg, mcp


def scrub_env(env: dict[str, str]) -> dict[str, str]:
    """``env`` without inherited Claude Code / Anthropic variables, except the OAuth token."""
    return {k: v for k, v in env.items() if k == TOKEN_VAR or not k.startswith(ENV_SCRUB_PREFIXES)}


class TokenCommandError(RuntimeError):
    """:data:`TOKEN_CMD_VAR` failed or printed no token (the message never holds its output)."""


def fetch_token(cmd: str, timeout: float = TOKEN_CMD_TIMEOUT_S) -> str:
    """Run ``cmd`` (no shell) and return its stdout, stripped. Its output is never logged."""
    try:
        argv = shlex.split(cmd)
    except ValueError as exc:
        raise TokenCommandError(f"{TOKEN_CMD_VAR} is not a valid command line: {exc}") from None
    if not argv:
        raise TokenCommandError(f"{TOKEN_CMD_VAR} is empty")
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TokenCommandError(f"{TOKEN_CMD_VAR} could not run: {type(exc).__name__}") from None
    token = res.stdout.strip()
    if res.returncode != 0:
        raise TokenCommandError(f"{TOKEN_CMD_VAR} exited with code {res.returncode}")
    if not token or any(c.isspace() for c in token):
        raise TokenCommandError(f"{TOKEN_CMD_VAR} did not print a single-line token")
    return token


def with_fresh_token(env: dict[str, str]) -> dict[str, str]:
    """``env`` without :data:`TOKEN_CMD_VAR`; when that variable is set in the harness's
    environment, :data:`TOKEN_VAR` holds a token fetched from it just now."""
    out = {k: v for k, v in env.items() if k != TOKEN_CMD_VAR}
    cmd = os.environ.get(TOKEN_CMD_VAR, "").strip()
    if cmd:
        out[TOKEN_VAR] = fetch_token(cmd)
        _register_secret(out[TOKEN_VAR])
    return out


def _register_secret(value: str) -> None:
    try:
        import sanitize  # same directory; optional so this module stays importable alone
    except ImportError:
        return
    sanitize.register_secret(value)


def agent_env(env: dict[str, str], config_dir: Path) -> dict[str, str]:
    """``run_eval.build_agent_env`` output adapted for Claude Code (TMPDIR is already per attempt).
    The OAuth token comes from :func:`with_fresh_token`."""
    out = with_fresh_token(scrub_env(env))
    out.update(ISOLATION_ENV)
    out["CLAUDE_CONFIG_DIR"] = str(config_dir)
    if out.get("TMPDIR"):
        out["CLAUDE_CODE_TMPDIR"] = out["TMPDIR"]
        # zsh (the Bash tool's shell on macOS) writes heredoc temp files to $TMPPREFIX,
        # /tmp/zsh by default, which the sandbox denies.
        out["TMPPREFIX"] = os.path.join(out["TMPDIR"], "zsh")
    return out


def command(model: str, max_turns: int, prompt: str, mcp_config: Path) -> list[str]:
    return [CLAUDE_BIN, "-p", "--model", model, "--max-turns", str(max_turns), "--output-format", "stream-json",
            "--verbose", "--dangerously-skip-permissions", "--strict-mcp-config", f"--mcp-config={mcp_config}",
            "--", prompt]


def inventory_command(model: str, mcp_config: Path) -> list[str]:
    """Local ``/context``: prints the init event and the context breakdown, no model call."""
    return [CLAUDE_BIN, "-p", "--model", model, "--output-format", "stream-json", "--verbose",
            "--strict-mcp-config", f"--mcp-config={mcp_config}", "--", "/context"]


def version() -> str:
    try:
        res = subprocess.run([CLAUDE_BIN, "--version"], capture_output=True, text=True, timeout=60,
                             env=scrub_env(dict(os.environ)))
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return res.stdout.strip().split(" ")[0] if res.returncode == 0 else ""


def binary_paths() -> list[str]:
    """The ``claude`` launcher and its resolved binary (for the sandbox read allowlist)."""
    found = shutil.which(CLAUDE_BIN)
    if not found:
        return []
    out = [found, os.path.realpath(found)]
    return [p for i, p in enumerate(out) if p not in out[:i]]


def ancestor_memory_files(path: Path, stop: Path | None = None) -> list[str]:
    """CLAUDE.md / AGENTS.md / ``.claude/CLAUDE.md`` / ``.claude/rules`` above ``path``.

    Claude Code loads these from every ancestor of the workspace;
    :data:`ISOLATION_ENV` disables that, and this records what it hides.
    """
    found = []
    for d in [path, *path.parents]:
        for name in ANCESTOR_MEMORY_FILES:
            if (d / name).exists():
                found.append(str(d / name))
        if stop is not None and d == stop:
            break
    return found


# --------------------------------------------------------------------------
# Inventory (pure)
# --------------------------------------------------------------------------


def init_event(events: list[dict]) -> dict | None:
    return next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), None)


def _context_text(events: list[dict]) -> str:
    out = []
    for e in events:
        if e.get("type") == "assistant":
            for b in (e.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "text":
                    out.append(str(b.get("text") or ""))
    return "\n".join(out)


def _section_rows(text: str, heading: str) -> list[list[str]]:
    """Table rows (cells) under ``### <heading>`` in ``/context`` output, header excluded."""
    m = re.search(rf"^#+\s*{re.escape(heading)}\s*$(.*?)(?=^#+\s|\Z)", text, re.M | re.S | re.I)
    if not m:
        return []
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or re.match(r"^\|[\s:|-]+\|$", line):
            continue
        rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows[1:]


def parse_context(text: str) -> dict:
    """``{"skills": [{"name", "source"}], "memory_files": [...]}`` from ``/context`` output."""
    skills = [{"name": r[0], "source": r[1] if len(r) > 1 else ""} for r in _section_rows(text, "Skills") if r]
    memory = [r[0] for r in _section_rows(text, "Memory files") if r]
    return {"skills": skills, "memory_files": memory}


def inventory_from_events(events: list[dict], with_context: bool = False) -> dict | None:
    """Inventory recorded per attempt (from the init event) or per campaign (+ ``/context``)."""
    init = init_event(events)
    if init is None:
        return None
    inv = {
        "skills": list(init.get("skills") or []),
        "plugins": [{k: p.get(k) for k in ("name", "path", "source")} for p in init.get("plugins") or []
                    if isinstance(p, dict)],
        "mcp_servers": init.get("mcp_servers") or [],
        "agents": list(init.get("agents") or []),
        "tools": list(init.get("tools") or []),
        "model": init.get("model"),
        "permission_mode": init.get("permissionMode"),
        "api_key_source": init.get("apiKeySource"),
        "claude_code_version": init.get("claude_code_version"),
        "memory_paths": init.get("memory_paths"),
    }
    if with_context:
        inv.update({"context_" + k: v for k, v in parse_context(_context_text(events)).items()})
    return inv


def check_inventory(arm: str, inv: dict | None, airflow_names: list[str], repo_names: list[str]) -> list[str]:
    """Problems with a Claude Code inventory (empty list = OK). Pure; unit-tested.

    Every repo skill must be listed, the Airflow skills only in the skill arm, no
    MCP server, only built-in plugins, no auto-memory dir, and (when ``/context``
    output is present) no memory file and no non-built-in skill outside the arm spec.
    """
    if inv is None:
        return ["no system/init event in the stream"]
    problems = []
    skills = set(inv.get("skills") or [])
    for n in repo_names:
        if n not in skills:
            problems.append(f"repo skill {n!r} missing")
    for n in airflow_names:
        if arm == "skill" and n not in skills:
            problems.append(f"airflow skill {n!r} missing in skill arm")
        if arm == "baseline" and n in skills:
            problems.append(f"airflow skill {n!r} present in baseline arm")
    if inv.get("mcp_servers"):
        problems.append(f"MCP servers loaded: {inv['mcp_servers']}")
    for p in inv.get("plugins") or []:
        if p.get("path") != "builtin":
            problems.append(f"non-builtin plugin loaded: {p.get('source') or p.get('name')}")
    if inv.get("memory_paths"):
        problems.append(f"auto-memory enabled: {inv['memory_paths']}")
    if inv.get("context_memory_files"):
        problems.append(f"memory files loaded: {inv['context_memory_files']}")
    expected = set(repo_names) | (set(airflow_names) if arm == "skill" else set())
    for s in inv.get("context_skills") or []:
        if s.get("source", "").lower() not in ("built-in", "builtin", "bundled") and s["name"] not in expected:
            problems.append(f"unexpected {s.get('source') or 'unknown'} skill {s['name']!r}")
    return problems


# --------------------------------------------------------------------------
# Running: stream monitor, usage-limit gate
# --------------------------------------------------------------------------


class StreamMonitor:
    """Incremental reader of a stream-json file while Claude Code runs.

    ``poll()`` parses complete new lines, keeps the running API-equivalent cost
    (``grading.claude_running_cost``) and, on the init event, runs ``on_init(inv)``;
    a non-empty problem list sets ``abort_reason`` so the caller stops the run.
    """

    def __init__(self, path: Path, model: str, cost_fn: Callable[[list[dict], str], float],
                 on_init: Callable[[dict | None], list[str]] | None = None) -> None:
        self.path, self.model, self._cost_fn, self._on_init = path, model, cost_fn, on_init
        self.events: list[dict] = []
        self.offset = 0
        self.cost = 0.0
        self.abort_reason: str | None = None
        self.inventory: dict | None = None
        self.inventory_problems: list[str] | None = None

    def poll(self) -> float:
        try:
            with self.path.open("rb") as fh:
                fh.seek(self.offset)
                data = fh.read()
        except FileNotFoundError:
            return self.cost
        end = data.rfind(b"\n")
        if end < 0:
            return self.cost
        self.offset += end + 1
        new = []
        for line in data[: end + 1].splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict):
                new.append(e)
        self.events.extend(new)
        if self.inventory_problems is None and any(e.get("type") == "system" and e.get("subtype") == "init"
                                                   for e in new):
            self.inventory = inventory_from_events(self.events)
            self.inventory_problems = self._on_init(self.inventory) if self._on_init else []
            if self.inventory_problems:
                self.abort_reason = "inventory mismatch: " + "; ".join(self.inventory_problems)
        if any(e.get("type") in ("assistant", "result") for e in new):
            self.cost = self._cost_fn(self.events, self.model)
        return self.cost


def is_usage_limit(record: dict) -> bool:
    """True when an infra error is a subscription usage/plan limit (pause, do not burn retries)."""
    if record.get("status") != "infra_error":
        return False
    text = "\n".join([str(record.get("reason") or "")] + [str(e) for e in record.get("errors") or []])
    return bool(USAGE_LIMIT.search(text))


def infra_backoff_s(attempt: int) -> float:
    """Wait before retry ``attempt`` (1-based) after a transient infra error: 30, 60, 120 s."""
    return INFRA_BACKOFF_S * 2 ** (attempt - 1)


class UsageLimitGate:
    """Campaign-wide pause after a usage limit.

    ``report_limit()`` pauses every worker for the next backoff step (2, 4, 8, 16
    min, ...) until the total pause would exceed ``max_wait_s``; then the gate
    stops and no new attempt starts. ``report_ok()`` resets the backoff.
    ``wait()`` blocks while paused and returns False once stopped.
    """

    def __init__(self, max_wait_s: float = USAGE_LIMIT_MAX_WAIT_S, first_wait_s: float = USAGE_LIMIT_FIRST_WAIT_S,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 log: Callable[[str], None] | None = None) -> None:
        self.max_wait_s, self.first_wait_s = max_wait_s, first_wait_s
        self._clock, self._sleep, self._log = clock, sleep, log or (lambda _m: None)
        self._lock = threading.Lock()
        self.level = 0
        self.waited_s = 0.0
        self.paused_until = 0.0
        self.stopped = False
        self.events: list[dict] = []

    def report_limit(self, detail: str = "") -> bool:
        """Record a usage limit; returns False when the campaign must stop."""
        with self._lock:
            now = self._clock()
            if self.stopped:
                return False
            if now < self.paused_until:  # another worker already paused for this limit
                return True
            step = self.first_wait_s * 2 ** self.level
            if self.waited_s + step > self.max_wait_s:
                step = self.max_wait_s - self.waited_s
            if step <= 0:
                self.stopped = True
                self.events.append({"action": "stop", "waited_s": self.waited_s, "detail": detail[:300]})
                self._log(f"USAGE LIMIT: paused {self.waited_s / 60:.0f} min in total; stopping the campaign "
                          "(rerun the same command with --resume)")
                return False
            self.level += 1
            self.waited_s += step
            self.paused_until = now + step
            self.events.append({"action": "pause", "seconds": step, "detail": detail[:300]})
            self._log(f"USAGE LIMIT: pausing all workers for {step / 60:.1f} min ({detail[:120]})")
            return True

    def report_ok(self) -> None:
        with self._lock:
            self.level = 0

    def wait(self) -> bool:
        while True:
            with self._lock:
                if self.stopped:
                    return False
                left = self.paused_until - self._clock()
            if left <= 0:
                return True
            self._sleep(min(left, 30))
