#!/usr/bin/env python3
"""Prove a pytest suite catches planted bugs, then put the code back exactly.

Runs the suite on the unmodified code (it must pass), then, one at a time, applies
each mutation (an exact text replacement in a source file), runs the suite again,
and restores the original bytes and mtime. A mutation is "caught" when pytest
reports at least one failing or erroring test (JUnit) with it applied. A run that
times out or ends without a failing test (pytest internal/usage error, no tests
collected, killed) is "inconclusive": it proves nothing either way.
SIGINT, SIGTERM and SIGHUP restore immediately. SIGKILL cannot be handled: rerun
from the same --cwd to restore the saved .mutation-check.json journal before
validating mutations or running tests. Do not delete that journal after a crash.

Stdlib only; run it with the Python that has Airflow and pytest installed.

Examples:
  python mutation_check.py \\
      --mutation dags/orders.py 'retries=2' 'retries=0' \\
      --mutation dags/orders.py 'extract >> load' 'load'
  python mutation_check.py --spec mutations.json -- tests/ -k "not slow"

Spec file format: [{"file": "...", "old": "...", "new": "...", "why": "..."}]

Exit codes:
  0  baseline passes and every mutation is caught
  1  the suite does not pass (or collects no tests) on the unmodified code
  2  at least one mutation survived (the suite still passed with the bug in place)
     or was inconclusive
  3  usage problem: bad arguments, missing file, or OLD text not found exactly once
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_LIST = 10
MAX_MSG = 300
DEFAULT_TIMEOUT = 900


class UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse exits 2 by default; 2 means "survived" here
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        sys.exit(3)


def parse_args(argv):
    p = _Parser(
        description=__doc__.split("\n\n")[0],
        epilog=__doc__[__doc__.index("Exit codes:"):],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--mutation", nargs=3, action="append", default=[],
                   metavar=("FILE", "OLD", "NEW"),
                   help="replace the exact text OLD (must occur once) with NEW in FILE")
    p.add_argument("--spec", help="JSON file with a list of {file, old, new, why}")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                   help=f"seconds per pytest run (default {DEFAULT_TIMEOUT})")
    p.add_argument("--cwd", default=".", help="directory to run pytest from (default: .)")
    p.add_argument("pytest_args", nargs="*",
                   help="arguments for pytest after '--' (default: tests)")
    return p.parse_args(argv)


def load_mutations(args, cwd: Path):
    muts = [{"file": f, "old": o, "new": n, "why": ""} for f, o, n in args.mutation]
    if args.spec:
        try:
            data = json.loads(Path(args.spec).read_text())
        except (OSError, ValueError) as e:
            raise UsageError(f"cannot read spec {args.spec}: {e}")
        if not isinstance(data, list):
            raise UsageError("spec must be a JSON list of {file, old, new}")
        for i, m in enumerate(data):
            if not isinstance(m, dict) or not all(isinstance(m.get(k), str) for k in ("file", "old", "new")):
                raise UsageError(f"spec item {i} needs string keys file, old, new")
            muts.append({"file": m["file"], "old": m["old"], "new": m["new"], "why": str(m.get("why", ""))})
    if not muts:
        raise UsageError("give at least one --mutation FILE OLD NEW or --spec FILE")
    for i, m in enumerate(muts):
        path = (cwd / m["file"]).resolve()
        if not path.is_file():
            raise UsageError(f"mutation {i}: file not found: {m['file']}")
        if m["old"] == m["new"]:
            raise UsageError(f"mutation {i}: OLD and NEW are identical")
        try:
            text = path.read_bytes().decode()  # same representation the mutation is applied to
        except UnicodeDecodeError as e:
            raise UsageError(f"mutation {i}: {m['file']} is not UTF-8 text: {e}")
        count = text.count(m["old"])
        if count != 1:
            raise UsageError(
                f"mutation {i}: OLD text occurs {count} times in {m['file']}; "
                "it must occur exactly once (include more surrounding text)")
        m["path"] = path
    return muts


def run_pytest(pytest_args, cwd: Path, timeout: int):
    with tempfile.TemporaryDirectory(prefix="mutcheck-") as tmp:
        junit = Path(tmp) / "junit.xml"
        cmd = [sys.executable, "-m", "pytest", *pytest_args, "-q", "-p", "no:cacheprovider",
               f"--junitxml={junit}"]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        start = time.time()
        try:
            proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                                  timeout=timeout)
            code, tail = proc.returncode, (proc.stdout + proc.stderr)[-MAX_MSG * 4:]
        except subprocess.TimeoutExpired:
            return {"exit_code": None, "timed_out": True, "passed": 0, "failed": 0,
                    "errors": 0, "failing": [], "collection_only": False,
                    "seconds": round(time.time() - start, 1)}
        res = parse_junit(junit)
        res.update(exit_code=code, timed_out=False, seconds=round(time.time() - start, 1))
        if code not in (0, 1) or (code == 1 and not res["failing"]):
            res["output_tail"] = tail
        return res


def parse_junit(path: Path):
    res = {"passed": 0, "failed": 0, "errors": 0, "failing": [], "collection_only": False}
    if not path.is_file():
        return res
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return res
    collection, behavioural = 0, 0
    for case in root.iter("testcase"):
        bad = case.find("failure")
        if bad is None:
            bad = case.find("error")
        if case.find("skipped") is not None:
            continue
        if bad is None:
            res["passed"] += 1
            continue
        name = "::".join(x for x in (case.get("classname"), case.get("name")) if x)
        msg = (bad.get("message") or "").strip().replace("\n", " ")[:MAX_MSG]
        is_collection = "collection failure" in msg
        if is_collection and bad.text:
            lines = [ln.strip() for ln in bad.text.strip().splitlines() if ln.strip()]
            msg = f"collection failure: {lines[-1][:MAX_MSG]}" if lines else msg
        if bad.tag == "failure":
            res["failed"] += 1
        else:
            res["errors"] += 1
        if is_collection:
            collection += 1
        else:
            behavioural += 1
        if len(res["failing"]) < MAX_LIST:
            res["failing"].append({"test": name, "kind": "collection" if is_collection else bad.tag,
                                   "message": msg})
    res["collection_only"] = collection > 0 and behavioural == 0
    return res


def _raise_interrupt(signum, frame):
    """Route termination and terminal hangup through the restore finally-block."""
    raise KeyboardInterrupt


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@contextmanager
def project_lock(cwd: Path):
    # Keep the lock inode: unlinking it lets a third runner bypass an existing waiter.
    with (cwd / ".mutation-check.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise UsageError(f"another mutation check is active in {cwd}") from None
        yield


def save_journal(journal: Path, path: Path, original: bytes, st):
    record = {"path": str(path), "original": base64.b64encode(original).decode("ascii"),
              "sha256": sha(original), "atime_ns": st.st_atime_ns, "mtime_ns": st.st_mtime_ns}
    # Publish a complete, flushed backup before touching the source file. A killed
    # writer can leave a temporary file, but cannot publish a partial journal.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=journal.parent,
                                         prefix=".mutation-check-", delete=False) as backup:
            temporary = Path(backup.name)
            json.dump(record, backup)
            backup.flush()
            os.fsync(backup.fileno())
        os.replace(temporary, journal)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def restore_journal(journal: Path):
    if not journal.exists():
        return
    record = json.loads(journal.read_text())
    original = base64.b64decode(record["original"], validate=True)
    if sha(original) != record["sha256"]:
        raise UsageError(f"backup checksum failed; preserve {journal} for manual recovery")
    path = Path(record["path"])
    with path.open("wb") as source:
        source.write(original)
        source.flush()
        os.fsync(source.fileno())
    os.utime(path, ns=(record["atime_ns"], record["mtime_ns"]))
    if sha(path.read_bytes()) != record["sha256"]:
        raise UsageError(f"restore failed; preserve {journal} for manual recovery")
    journal.unlink()


def main(argv=None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        cwd = Path(args.cwd).resolve()
        if not cwd.is_dir():
            raise UsageError(f"--cwd is not a directory: {args.cwd}")
        signal.signal(signal.SIGTERM, _raise_interrupt)
        signal.signal(signal.SIGHUP, _raise_interrupt)
        with project_lock(cwd):
            journal = cwd / ".mutation-check.json"
            restore_journal(journal)  # before OLD validation, which a stranded mutation fails
            muts = load_mutations(args, cwd)
            return run_mutations(args, cwd, muts, journal)
    except (UsageError, OSError, ValueError) as e:
        print(json.dumps({"error": str(e), "exit_code": 3}))
        return 3


def run_mutations(args, cwd: Path, muts: list, journal: Path) -> int:
    pytest_args = args.pytest_args or ["tests"]

    out = {"python": sys.executable, "cwd": str(cwd), "pytest_args": pytest_args}
    baseline = run_pytest(pytest_args, cwd, args.timeout)
    out["baseline"] = baseline
    if baseline["exit_code"] != 0 or baseline["passed"] == 0:
        out["summary"] = {"mutations": len(muts), "caught": 0, "survived": 0,
                          "note": "suite must pass on the unmodified code before mutations mean anything"}
        out["restored"] = True
        out["exit_code"] = 1
        print(json.dumps(out, indent=1))
        return 1

    results, restored_ok = [], True
    for i, m in enumerate(muts):
        path: Path = m["path"]
        original = path.read_bytes()
        st = path.stat()
        entry = {"id": i, "file": m["file"], "old": m["old"][:MAX_MSG], "new": m["new"][:MAX_MSG],
                 "why": m["why"][:MAX_MSG]}
        try:
            mutated = original.decode().replace(m["old"], m["new"], 1).encode()
            save_journal(journal, path, original, st)
            path.write_bytes(mutated)
            # A different mtime forces Python to recompile instead of reusing a cached .pyc.
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
            run = run_pytest(pytest_args, cwd, args.timeout)
        finally:
            restore_journal(journal)
            if sha(path.read_bytes()) != sha(original):
                restored_ok = False
        caught = run["exit_code"] in (1, 2) and bool(run["failing"])
        inconclusive = not caught and run["exit_code"] != 0
        entry.update(caught=caught, inconclusive=inconclusive, exit_code=run["exit_code"],
                     timed_out=run["timed_out"], caught_by=run["failing"],
                     collection_only=run["collection_only"])
        if "output_tail" in run:
            entry["output_tail"] = run["output_tail"]
        results.append(entry)

    survived = [r["id"] for r in results if not r["caught"] and not r["inconclusive"]]
    inconclusive = [r["id"] for r in results if r["inconclusive"]]
    out["mutants"] = results
    out["restored"] = restored_ok
    out["summary"] = {
        "mutations": len(results),
        "caught": len(results) - len(survived) - len(inconclusive),
        "survived": len(survived),
        "survived_ids": survived,
        "inconclusive_ids": inconclusive,
        "caught_only_by_collection_error": [r["id"] for r in results if r["caught"] and r["collection_only"]],
    }
    out["exit_code"] = 2 if survived or inconclusive else 0
    print(json.dumps(out, indent=1))
    return out["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
