"""Grader for testing-custom-operator-conn (Airflow 3.3).

The agent writes a pytest suite. Grading runs that suite, never the agent's claims:

1. Against the correct project (the pristine fixture sources restored over the
   agent's workspace): the suite must collect at least one test and pass.
2. Against each hidden planted-bug variant (``hidden_bugs/<name>/`` overlays the
   agent never sees): at least one test must fail for a behavioural reason. A
   test-module collection error does not count. For planted import errors, a
   test that fails at run time because the DAG file cannot be imported does count
   (that is exactly what a loader test is for).
3. Against a behaviour-preserving edit of the sources (a comment added at the top
   and bottom of every ``dags/**/*.py`` plus an unused ``__review_note__`` module
   attribute): the suite must still pass. This rejects snapshot suites (hashing or
   diffing the DAG files or their AST) that "catch" every planted bug without
   testing any behaviour.

Each pytest run gets its own AIRFLOW_HOME with a migrated sqlite metadata DB (what a
CI job has after ``airflow db migrate``); no scheduler or other services run.
The hidden-bug and pristine-restore logic is shared by every ``testing-*`` case.
"""

from __future__ import annotations

import concurrent.futures as cf
import filecmp
import os
import shutil
import sys
import tempfile
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

# Fixture paths restored before running the agent's suite (the code under test).
SOURCE_PATHS = ("dags", "data")
# name -> (what the planted bug is, whether it is an import-time failure)
HIDDEN_BUGS = {
    "hook_ignores_host": ("hook reads the DuckDB path from extra['path'] (default :memory:), not conn.host", False),
    "schema_from_extra": ("hook reads the target schema from extra['schema'] instead of conn.schema", False),
    "conn_id_ignored": ("operator builds the hook with the default conn id, ignoring duckdb_conn_id", False),
    "rerun_duplicates": ("operator no longer deletes the partition before inserting (re-runs duplicate)", False),
    "partition_filter_dropped": ("operator inserts every row of the CSV, not just partition_date", False),
}
PYTEST_TIMEOUT = 300
BENIGN_HEADER = "# Reviewed in PR: formatting only, behaviour unchanged.\n"
# A no-op module attribute as well as comments, so a suite that snapshots the code
# (AST or bytecode) rather than the text still counts as a snapshot suite.
BENIGN_FOOTER = '\n\n# End of module.\n__review_note__ = "formatting only, behaviour unchanged"\n'


def pristine_overlay(tmp: Path) -> Path:
    """Overlay holding the fixture's source files (tests and configs excluded)."""
    ov = tmp / "pristine"
    for rel in SOURCE_PATHS:
        src = CASE_DIR / "fixture" / rel
        if src.is_dir():
            shutil.copytree(src, ov / rel, ignore=shutil.ignore_patterns("__pycache__"))
        elif src.exists():
            (ov / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, ov / rel)
    return ov


def benign_overlay(tmp: Path) -> Path:
    """Overlay with every fixture ``dags/**/*.py`` wrapped in comments plus a no-op attribute."""
    ov = tmp / "benign"
    root = CASE_DIR / "fixture"
    for src in (root / "dags").rglob("*.py"):
        if "__pycache__" in src.parts:
            continue
        dst = ov / src.relative_to(root)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(BENIGN_HEADER + src.read_text().rstrip("\n") + BENIGN_FOOTER)
    return ov


def migrated_home(py: str, tmp: Path) -> Path:
    home = tmp / "af-home-template"
    res = g.ensure_db(py, g.airflow_env(tmp, airflow_home=home, env_py=py))
    if not res.ok:
        raise RuntimeError(f"airflow db migrate failed: {res.tail()}")
    return home


def run_suite(py: str, ws: Path, home_template: Path) -> g.PytestResult:
    home = Path(tempfile.mkdtemp(prefix="eval-af-home-"))
    shutil.copytree(home_template, home, dirs_exist_ok=True)
    env = g.airflow_env(ws, airflow_home=home, env_py=py)
    return g.run_pytest(py, ws, ("tests",), env=env, timeout=PYTEST_TIMEOUT,
                        extra_args=("--continue-on-collection-errors",))


def caught(res: g.PytestResult, import_kind: bool) -> bool:
    if res.status == "timeout":
        return False
    if import_kind:
        return any(t.outcome in ("failed", "error") and t.phase != "collection" for t in res.tests)
    return bool(res.behavioral_failures)


def test_files(ws: Path) -> list[Path]:
    tests = ws / "tests"
    if not tests.is_dir():
        return []
    return sorted(set(tests.rglob("test_*.py")) | set(tests.rglob("*_test.py")))


def changed_sources(ws: Path) -> list[str]:
    changed = []
    for rel in SOURCE_PATHS:
        root = CASE_DIR / "fixture" / rel
        files = [p for p in root.rglob("*") if p.is_file()] if root.is_dir() else [root]
        for f in files:
            r = f.relative_to(CASE_DIR / "fixture")
            if "__pycache__" in r.parts:
                continue
            if not (ws / r).is_file() or not filecmp.cmp(f, ws / r, shallow=False):
                changed.append(str(r))
    return changed


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)
    tmp = Path(tempfile.mkdtemp(prefix="eval-testing-"))

    files = test_files(ws)
    grader.primary("test suite exists under tests/", bool(files),
                   ", ".join(str(f.relative_to(ws)) for f in files) or "no test_*.py files under tests/")

    home = migrated_home(py, tmp)
    correct = g.copy_workspace(ws, [pristine_overlay(tmp)])
    base = run_suite(py, correct, home)
    base_ok = base.status == "passed" and base.passed >= 1
    grader.primary("suite passes on the correct project", base_ok,
                   base.summary() + ("" if base_ok else "\n" + base.output_tail[-2500:]))

    benign_ov = benign_overlay(tmp)

    def job(name: str):
        overlay = benign_ov if name == "__benign__" else CASE_DIR / "hidden_bugs" / name
        return name, run_suite(py, g.copy_workspace(correct, [overlay]), home)

    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        results = dict(ex.map(job, ["__benign__", *HIDDEN_BUGS]))
    benign = results.pop("__benign__")
    benign_ok = base_ok and benign.status == "passed" and benign.passed >= 1
    grader.primary("suite passes on a behaviour-preserving edit of the sources", benign_ok,
                   ("" if base_ok else "not attributable: the suite does not pass on the correct project; ")
                   + benign.summary() + ("" if benign_ok or not base_ok else "\n" + benign.output_tail[-1500:]))
    for name, (what, import_kind) in HIDDEN_BUGS.items():
        res = results[name]
        hit = base_ok and caught(res, import_kind)
        prefix = "" if base_ok else "not attributable: the suite does not pass on the correct project; "
        grader.primary(f"suite catches hidden bug: {name}", hit, f"{prefix}{what} -> {res.summary()}")

    changed = changed_sources(ws)
    grader.secondary("project sources left unchanged", not changed, ", ".join(changed[:20]))
    g.standard_secondary_checks(grader, py, correct, events, verify_patterns=(r"\bpytest\b",),
                                ruff_paths=("tests",) if files else ("dags",))
    grader.write(args.out)


if __name__ == "__main__":
    main()
