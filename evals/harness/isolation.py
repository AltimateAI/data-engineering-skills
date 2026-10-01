"""Agent isolation for eval runs: macOS sandbox profile, contamination scan and
agent-venv fingerprint/restore. Standard library only.

- :func:`sandbox_profile` renders a ``sandbox-exec`` (SBPL) profile that denies
  file writes outside an allowlist (the attempt's scratch dir, the agent venv,
  altimate-code's cache, ``/dev``) and denies reads of the repo checkout, the
  results dir, other attempts' scratch dirs and the host's shared altimate-code
  data. SBPL is last-match-wins, so later ``allow`` rules punch holes in
  earlier ``deny`` rules. Signals are allowed only to processes of the same
  sandbox instance, so an agent's ``pkill -f airflow`` cannot reach the harness,
  graders or sibling runs (each ``sandbox-exec`` call is its own instance).
  Process information is restricted to that instance too, and process-table
  sysctl reads are denied to prevent exposure of outside command arguments.
- :func:`scan_kill_commands` flags bash commands that kill processes by name or
  pattern (``pkill``, ``killall``, ``kill`` fed by ``pgrep``/``ps``/``lsof``, ``kill -1``).
- :func:`scan_contamination` inspects a run's tool calls for references to
  paths outside the attempt (``/tmp``, the repo, other attempts, ...). It works
  without the sandbox and also records what the sandbox blocked.
- :func:`venv_fingerprint` / :class:`AgentEnvGuard` detect and undo changes the
  agent makes to its shared Airflow venv.
"""

from __future__ import annotations

import hashlib
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# --------------------------------------------------------------------------
# sandbox-exec
# --------------------------------------------------------------------------

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
#: Signals only within the same sandbox instance: a sandboxed ``kill``/``pkill`` of an
#: outside process (harness, grader, sibling run) fails with EPERM.
SIGNAL_RULES = ("(deny signal)", "(allow signal (target same-sandbox))")
# Both controls are necessary on macOS: process-info alone does not hide argv
# retrieved through sysctl, and sysctl alone does not block known-PID queries.
PROCESS_INFO_RULES = (
    '(deny sysctl-read (sysctl-name-prefix "kern.proc"))',
    "(deny process-info*)",
    "(allow process-info* (target same-sandbox))",
)


def _sbpl_str(path: str | os.PathLike) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _real(path: str | os.PathLike) -> str:
    """Resolved path: the sandbox matches real paths (``/tmp`` is ``/private/tmp``)."""
    return os.path.realpath(os.path.expanduser(str(path)))


def _filters(paths: Iterable[str | os.PathLike], kind: str = "subpath") -> str:
    seen: list[str] = []
    for p in paths:
        rp = _real(p)
        if rp not in seen:
            seen.append(rp)
    return " ".join(f"({kind} {_sbpl_str(p)})" for p in seen)


def sandbox_profile(
    write_allow: Iterable[str | os.PathLike],
    read_deny: Iterable[str | os.PathLike] = (),
    read_allow: Iterable[str | os.PathLike] = (),
    read_allow_literal: Iterable[str | os.PathLike] = (),
    metadata_allow_literal: Iterable[str | os.PathLike] = (),
    isolate_signals: bool = True,
) -> str:
    """SBPL profile text. Everything not listed keeps the default (allowed).

    Order matters (last match wins): writes are denied globally then allowed
    under ``write_allow``; reads are denied under ``read_deny`` then re-allowed
    under ``read_allow`` (subpaths) and ``read_allow_literal`` (single files).
    ``metadata_allow_literal`` re-allows only ``stat``/``lstat`` of single paths (not
    listing or reading them): the ancestors of an allowed dir inside a denied root,
    which ``mkdir -p`` and SQLite's path resolution walk.
    ``isolate_signals`` denies signals except to processes of the same sandbox
    instance (the agent's own process tree), and hides outside process info.
    """
    lines = ["(version 1)", "(allow default)", "(deny file-write*)"]
    writes = _filters(write_allow)
    lines.append(f"(allow file-write* {writes} (literal \"/dev/null\"))" if writes
                 else '(allow file-write* (literal "/dev/null"))')
    deny = _filters(read_deny)
    if deny:
        lines.append(f"(deny file-read* {deny})")
        allow = " ".join(x for x in (_filters(read_allow), _filters(read_allow_literal, "literal")) if x)
        if allow:
            lines.append(f"(allow file-read* {allow})")
        meta = _filters(metadata_allow_literal, "literal")
        if meta:
            lines.append(f"(allow file-read-metadata {meta})")
    if isolate_signals:
        lines += PROCESS_INFO_RULES
        lines += SIGNAL_RULES
    return "\n".join(lines) + "\n"


_SANDBOX_OK: bool | None = None
_SANDBOX_LOCK = threading.Lock()


def sandbox_available() -> bool:
    """True on macOS when ``sandbox-exec`` runs a trivial profile."""
    global _SANDBOX_OK
    with _SANDBOX_LOCK:
        if _SANDBOX_OK is None:
            _SANDBOX_OK = False
            if sys.platform == "darwin" and Path(SANDBOX_EXEC).exists():
                try:
                    res = subprocess.run([SANDBOX_EXEC, "-p", "(version 1)(allow default)", "/usr/bin/true"],
                                         capture_output=True, timeout=30)
                    _SANDBOX_OK = res.returncode == 0
                except (OSError, subprocess.TimeoutExpired):
                    _SANDBOX_OK = False
        return _SANDBOX_OK


def sandbox_wrap(cmd: list[str], profile_path: str | os.PathLike) -> list[str]:
    return [SANDBOX_EXEC, "-f", str(profile_path), *cmd]


# --------------------------------------------------------------------------
# Contamination scan
# --------------------------------------------------------------------------

#: Temp roots shared between runs. A per-attempt TMPDIR lives under the attempt
#: scratch dir, so a reference to any of these is outside the attempt.
SHARED_TEMP_ROOTS = ("/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp", "/var/folders", "/private/var/folders")
_PATH_KEYS = ("filePath", "file_path", "path", "paths", "cwd", "workdir", "dir", "directory", "pattern", "include")
_ABS_PATH = re.compile(r"""(?:(?<=^)|(?<=[\s'"`=:;(|&<>,\[]))(~?/[^\s'"`;|&<>(){},\[\]*?$]+)""")
#: A bare "sandbox" is not denial evidence: a successful read of a file that merely contains the word
#: would hide the access.
_DENIED = re.compile(r"Operation not permitted|\bEPERM\b|sandbox(?:-exec)?\b[^\n]*\bdeny|\bdeny\b[^\n]*\bsandbox", re.I)


@dataclass
class ContaminationPolicy:
    """Roots the agent may not touch, with allowed holes inside them.

    ``forbidden``: (label, root) pairs. ``allowed``: roots that are fine even when
    nested in a forbidden root (the attempt scratch dir, the staged skills).
    ``home``: expands ``~`` in commands.
    """

    forbidden: list[tuple[str, str]]
    allowed: list[str] = field(default_factory=list)
    home: str = field(default_factory=lambda: os.path.expanduser("~"))


def _under(path: str, root: str) -> bool:
    root = root.rstrip("/") or "/"
    return path == root or path.startswith(root + "/")


def _norm(path: str, home: str) -> str:
    if path.startswith("~/") or path == "~":
        path = home + path[1:]
    return os.path.normpath(path)


def _equivalents(root: str) -> list[str]:
    """``root`` plus its resolved form (``/tmp`` vs ``/private/tmp``)."""
    out = [os.path.normpath(root)]
    real = os.path.realpath(root)
    if real not in out:
        out.append(real)
    return out


def classify_path(path: str, policy: ContaminationPolicy) -> str | None:
    """Label of the most specific forbidden root ``path`` falls under, or None."""
    p = _norm(path, policy.home)
    candidates = {p, os.path.realpath(p)} if os.path.isabs(p) else {p}
    for c in candidates:
        if any(_under(c, a) for al in policy.allowed for a in _equivalents(al)):
            return None
    best: tuple[int, str] | None = None
    for c in candidates:
        for label, root in policy.forbidden:
            for rt in _equivalents(root):
                if _under(c, rt) and (best is None or len(rt) > best[0]):
                    best = (len(rt), label)
    return best[1] if best else None


def paths_in_text(text: str) -> list[str]:
    """Absolute or ``~/`` paths mentioned in a shell command."""
    return [m.rstrip(".,:") for m in _ABS_PATH.findall(text or "")]


def _input_paths(tool: str, inp: dict) -> list[str]:
    if tool == "bash":
        return paths_in_text(str(inp.get("command") or "")) + paths_in_text(str(inp.get("workdir") or ""))
    out: list[str] = []
    for key in _PATH_KEYS:
        val = inp.get(key)
        vals = val if isinstance(val, list) else [val]
        for v in vals:
            if isinstance(v, str) and (v.startswith("/") or v.startswith("~")):
                out.append(v)
    return out


def scan_contamination(tool_calls: list[dict], policy: ContaminationPolicy) -> dict:
    """Check tool calls (``grading.tool_uses`` rows) for paths outside the attempt.

    Returns ``{"contamination_suspect", "hits", "denied_hits"}``. A hit whose tool
    output says the access was denied (sandbox ``Operation not permitted``) is
    recorded in ``denied_hits`` and does not make the run suspect.
    """
    hits, denied = [], []
    for i, u in enumerate(tool_calls):
        for path in _input_paths(str(u.get("tool") or ""), u.get("input") or {}):
            label = classify_path(path, policy)
            if not label:
                continue
            item = {"call": i, "tool": u.get("tool"), "path": path, "root": label}
            (denied if _DENIED.search(str(u.get("output") or "")) else hits).append(item)
    return {"contamination_suspect": bool(hits), "hits": hits[:50], "denied_hits": denied[:50]}


# --------------------------------------------------------------------------
# Broad kill commands
# --------------------------------------------------------------------------

#: Commands that kill processes by name or pattern instead of a known pid. They can
#: hit sibling runs, graders and the harness (the sandbox's signal rules block that).
_KILL_PATTERNS = (
    ("pkill", re.compile(r"(?<![\w.-])pkill\b")),
    ("killall", re.compile(r"(?<![\w.-])killall\b")),
    ("kill-substitution",
     re.compile(r"(?<![\w.-])kill\b[^;&|\n]*(?:\$\(|`)[^)`]*\b(?:pgrep|pidof|ps|lsof)\b")),
    ("xargs-kill", re.compile(r"\b(?:pgrep|pidof|ps|lsof)\b[^;&\n]*\|[^;&\n]*\bxargs\b[^;&|\n]*\bkill\b")),
    ("kill-all-pids", re.compile(r"(?<![\w.-])kill\s+(?:-\S+\s+)?-1(?=\s*$|\s*[;&|)])", re.M)),
)


def kill_patterns(command: str) -> list[str]:
    """Labels of the broad kill patterns in a shell command (empty = none)."""
    return [label for label, rx in _KILL_PATTERNS if rx.search(command or "")]


def scan_kill_commands(tool_calls: list[dict]) -> list[dict]:
    """Bash tool calls that kill processes by name or pattern: ``[{call, patterns, command, output}]``."""
    out = []
    for i, u in enumerate(tool_calls):
        if str(u.get("tool") or "") != "bash":
            continue
        cmd = str((u.get("input") or {}).get("command") or "")
        found = kill_patterns(cmd)
        if found:
            out.append({"call": i, "patterns": found, "command": cmd[:300],
                        "output": str(u.get("output") or "")[:200]})
    return out[:50]


# --------------------------------------------------------------------------
# Agent venv fingerprint and restore
# --------------------------------------------------------------------------

_FP_SKIP_DIRS: set[str] = set()


def _file_digest(path: str) -> str:
    h = hashlib.sha1()  # change detection, not security against collisions
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def venv_manifest(venv: str | os.PathLike) -> dict[str, str]:
    """``{relative path: signature}`` for every file and symlink in ``venv``.

    Files are signed by content hash, symlinks by target. Bytecode is included:
    the pristine venv has none (``setup_envs.sh`` removes it and agents run with
    ``PYTHONDONTWRITEBYTECODE=1``), so any ``.pyc`` is a change and is removed on
    restore. Content (not mtimes) keeps the manifest stable across a reinstall of
    identical packages.
    """
    root = Path(venv)
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        links = [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]
        dirnames[:] = [d for d in dirnames if d not in _FP_SKIP_DIRS and d not in links]
        for name in filenames + links:
            p = os.path.join(dirpath, name)
            rel = os.path.relpath(p, root)
            try:
                out[rel] = f"L {os.readlink(p)}" if os.path.islink(p) else f"F {_file_digest(p)}"
            except OSError:
                out[rel] = "?"
    return out


def manifest_fingerprint(manifest: dict[str, str]) -> str:
    h = hashlib.sha256()
    for rel in sorted(manifest):
        h.update(f"{rel}\0{manifest[rel]}\n".encode())
    return h.hexdigest()


def venv_fingerprint(venv: str | os.PathLike) -> str:
    """sha256 of :func:`venv_manifest` (``"missing"`` if the venv does not exist)."""
    return manifest_fingerprint(venv_manifest(venv)) if Path(venv).exists() else "missing"


def freeze_file(venv: str | os.PathLike) -> Path:
    """``<venv>.requirements.txt`` written by ``setup_envs.sh`` (outside the venv)."""
    v = Path(venv)
    return v.parent / f"{v.name}.requirements.txt"


def manifest_file(venv: str | os.PathLike) -> Path:
    v = Path(venv)
    return v.parent / f"{v.name}.manifest.json"


def write_pristine(venv: str | os.PathLike) -> str:
    """Record the venv's current state as pristine (``<venv>.manifest.json``); returns its fingerprint."""
    manifest = venv_manifest(venv)
    manifest_file(venv).write_text(json.dumps(manifest, sort_keys=True))
    return manifest_fingerprint(manifest)


def resync_venv(venv: str | os.PathLike, reinstall: bool = False, timeout: int = 900) -> subprocess.CompletedProcess:
    """``uv pip sync`` the venv back to its frozen requirements."""
    v = Path(venv)
    cmd = ["uv", "pip", "sync", "--python", str(v / "bin" / "python"), str(freeze_file(v))]
    if reinstall:
        cmd.insert(3, "--reinstall")
    env = {k: val for k, val in os.environ.items() if k not in ("VIRTUAL_ENV", "PIP_REQUIRE_VIRTUALENV")}
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def remove_extras(venv: str | os.PathLike, pristine: dict[str, str]) -> list[str]:
    """Delete files/symlinks not in the pristine manifest (e.g. dropped in without pip)."""
    root = Path(venv)
    removed = []
    for rel in sorted(set(venv_manifest(root)) - set(pristine)):
        try:
            (root / rel).unlink()
            removed.append(rel)
        except OSError:
            pass
    for dirpath, _dirs, _files in sorted(os.walk(root, topdown=False)):
        if dirpath != str(root) and not os.listdir(dirpath) and os.path.basename(dirpath) not in _FP_SKIP_DIRS:
            try:
                os.rmdir(dirpath)
            except OSError:
                pass
    return removed


class AgentEnvGuard:
    """Keeps an agent venv at its pristine state.

    The pristine manifest comes from ``<venv>.manifest.json`` (``setup_envs.sh``),
    or else from the venv as it is when the guard is created. ``check()``
    compares the venv with it and, when it differs, restores it: ``uv pip sync``
    to the frozen requirements, delete files that are not in the manifest, then
    ``uv pip sync --reinstall`` if the venv still differs. Returns
    ``{"changed", "restored", "detail"}``. ``attempt()`` holds an exclusive lease
    through the pre-check, agent execution and post-check. Threads and separate
    harness processes sharing a venv cannot restore it during another attempt.
    """

    def __init__(self, venv: str | os.PathLike, resync=resync_venv) -> None:
        self.venv = Path(venv)
        self._resync = resync
        self._lock = threading.RLock()
        self._lease_depth = 0
        with self.attempt():
            mf = manifest_file(self.venv)
            self.manifest = json.loads(mf.read_text()) if mf.exists() else venv_manifest(self.venv)
        self.pristine = manifest_fingerprint(self.manifest)
        self.restores = 0

    def _clean(self) -> bool:
        return venv_fingerprint(self.venv) == self.pristine

    @contextmanager
    def attempt(self):
        """Exclusive, reentrant venv lease; the lock file is outside the venv."""
        with self._lock:
            if self._lease_depth:
                self._lease_depth += 1
                try:
                    yield
                finally:
                    self._lease_depth -= 1
                return
            venv = self.venv.resolve()
            lock_path = venv.with_name(venv.name + ".attempt.lock")
            with lock_path.open("a+b") as lock_file:
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                self._lease_depth = 1
                try:
                    yield
                finally:
                    self._lease_depth = 0
                    fcntl.flock(lock_file, fcntl.LOCK_UN)

    def check(self) -> dict:
        with self.attempt():
            if self._clean():
                return {"changed": False, "restored": False, "detail": ""}
            now = venv_manifest(self.venv)
            diff = sorted(set(now) ^ set(self.manifest)) + sorted(
                k for k in set(now) & set(self.manifest) if now[k] != self.manifest[k])
            detail = [f"{len(diff)} path(s) differ, e.g. {diff[:3]}"]
            can_sync = freeze_file(self.venv).exists() and shutil.which("uv") is not None
            if can_sync:
                res = self._resync(self.venv, reinstall=False)
                detail.append(f"uv pip sync rc={res.returncode}")
            removed = remove_extras(self.venv, self.manifest)
            if removed:
                detail.append(f"removed {len(removed)} extra file(s)")
            if not self._clean() and can_sync:
                res = self._resync(self.venv, reinstall=True)
                detail.append(f"uv pip sync --reinstall rc={res.returncode}")
                remove_extras(self.venv, self.manifest)
            restored = self._clean()
            if restored:
                self.restores += 1
            elif not can_sync:
                detail.append(f"no {freeze_file(self.venv)} or uv")
            return {"changed": True, "restored": restored, "detail": "; ".join(detail)}
