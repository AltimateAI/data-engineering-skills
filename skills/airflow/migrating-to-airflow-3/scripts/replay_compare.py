#!/usr/bin/env python3
"""BEFORE/AFTER replay of a migrated Airflow project: same runs, same outputs?

Replays one plan of runs on two copies of the project, the untouched 2.x copy
(BEFORE) and the migrated copy (AFTER), then compares the per-run results and
every file under the output directories.

Each side gets its own fresh AIRFLOW_HOME and sqlite metadata DB, shared by all
DAGs of that side, so XComs, Variables and task history carry over between runs
and between DAGs (needed for include_prior_dates and cross-DAG state). The runs
themselves are executed by replay_runs.py (next to this script), one plan line
at a time, in plan order: put producers before consumers.

Plan file, one line per DAG (``#`` comments allowed), flags as for replay_runs.py:

    hourly_ingest  --runs 3 --from 2026-03-04T00:00:00Z
    daily_report   --runs 3 --from 2026-03-03 --manual 2026-03-06T09:15:00Z
    reprocess      --runs 0 --manual 2026-03-06T10:00:00Z --conf '{"day": "2026-03-04"}'

Usage (run with the 3.x project Python):

    python replay_compare.py --before DIR --after DIR --plan PLAN
        [--before-python PY2] [--legacy-before] [--outputs output ...]
        [--env KEY=VALUE ...] [--keep-outputs]

--before-python: a 2.x interpreter, when one exists (the real baseline).
--legacy-before: no 2.x interpreter. BEFORE runs on the 3.x Python with the
  2.x scheduler defaults switched back on (create_cron/delta_data_intervals,
  catchup_by_default = True). This reproduces 2.x schedule dates for bare cron
  / timedelta schedules; BEFORE runs that fail on removed 2.x-only keys have no
  baseline and are reported as such ("No baseline"), as are files only AFTER
  wrote; missing or changed files still count as differences. Manual runs also
  have no baseline: both sides use 3.x semantics (no logical date), so compare
  them against the 2.x behaviour by reasoning, even when outputs match.
--outputs: directories (relative to each copy) holding what the DAGs write;
  default "output". They are deleted in both copies before replaying unless
  --keep-outputs is given, so pass copies, never the working project.
--env: extra environment for both sides (AIRFLOW_CONN_*, AIRFLOW_VAR_*,
  AIRFLOW__SECTION__KEY options the project reads). Repeatable. ``{root}`` in a
  value becomes that side's copy, e.g. --env 'AIRFLOW_CONN_FS={"conn_type": "fs",
  "extra": {"path": "{root}/data"}}' or --env AIRFLOW__X__DROP_DIR={root}/output/drop.

stdout: a human-readable report; the last line is a JSON summary.
Exit codes: 0 identical, 2 differences (or a side failed to replay),
3 usage/environment error, 4 no differences but some runs/files had no
baseline (a failed BEFORE run, or emulated/absent baselines with --legacy-before),
so not proven. Both sides replay in parallel;
expect a few seconds per planned run.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPLAY = HERE / "replay_runs.py"
EXIT_OK, EXIT_DIFF, EXIT_USAGE, EXIT_UNPROVEN = 0, 2, 3, 4
LEGACY = {
    "AIRFLOW__SCHEDULER__CREATE_CRON_DATA_INTERVALS": "True",
    "AIRFLOW__SCHEDULER__CREATE_DELTA_DATA_INTERVALS": "True",
    "AIRFLOW__SCHEDULER__CATCHUP_BY_DEFAULT": "True",
}
RUN_FIELDS = ("kind", "logical_date", "run_after", "data_interval_start", "data_interval_end", "state")
MAX_DIFF_LINES = 12


class UsageError(Exception):
    pass


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--before", required=True, help="untouched 2.x copy of the project")
    p.add_argument("--after", required=True, help="migrated copy of the project")
    p.add_argument("--plan", required=True, help="plan file: one '<dag_id> <replay_runs flags>' per line")
    p.add_argument("--before-python", default=None, help="2.x interpreter for BEFORE (default: this one)")
    p.add_argument("--after-python", default=sys.executable, help="3.x interpreter for AFTER")
    p.add_argument("--legacy-before", action="store_true",
                   help="BEFORE on 3.x with the 2.x scheduler defaults (no 2.x env)")
    p.add_argument("--outputs", action="append", default=None, help="output dir(s), default 'output'")
    p.add_argument("--env", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("--keep-outputs", action="store_true", help="do not delete outputs before replaying")
    p.add_argument("--timeout", type=int, default=1800, help="seconds per plan line (default 1800)")
    try:
        return p.parse_args(argv)
    except SystemExit as exc:
        raise SystemExit(EXIT_USAGE if exc.code else 0) from None


def strip_comment(line: str) -> str:
    """Drop a ``#`` comment that starts a word outside quotes (``abc#def`` is kept)."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


def read_plan(path: str) -> list[tuple[str, list[str]]]:
    plan = []
    for number, raw in enumerate(Path(path).read_text().splitlines(), start=1):
        line = strip_comment(raw).strip()
        if not line:
            continue
        try:
            parts = shlex.split(line)
        except ValueError as exc:
            raise UsageError(f"plan line {number}: {exc}: {raw!r}") from None
        plan.append((parts[0], parts[1:]))
    if not plan:
        raise UsageError(f"plan file {path} has no runs")
    return plan


def side_env(root: Path, extra: dict, legacy: bool) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("AIRFLOW__")}
    home = Path(tempfile.mkdtemp(prefix="replay-compare-home-"))
    env.update({
        "AIRFLOW_HOME": str(home),
        "AIRFLOW__CORE__DAGS_FOLDER": str(root / "dags"),
        "AIRFLOW__CORE__LOAD_EXAMPLES": "False",
        "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN": f"sqlite:///{home / 'airflow.db'}",
        "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
        # A failing task with retries would otherwise wait the default 300 s per retry.
        "AIRFLOW__CORE__DEFAULT_TASK_RETRY_DELAY": "1",
    })
    # Cluster policy (Airflow's own hook): no retries, so a failing task fails its run at
    # once instead of waiting retry_delay (often minutes) inside the replay.
    (home / "airflow_local_settings.py").write_text(
        "def task_policy(task):\n    task.retries = 0\n")
    paths = [str(home), str(root)]
    if (root / "plugins").is_dir():
        env["AIRFLOW__CORE__PLUGINS_FOLDER"] = str(root / "plugins")
        paths.append(str(root / "plugins"))
    env["PYTHONPATH"] = os.pathsep.join(paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    if legacy:
        env.update(LEGACY)
    env.update({k: v.replace("{root}", str(root)) for k, v in extra.items()})
    return env


def replay_side(name: str, root: Path, python: str, plan, env: dict, timeout: int) -> dict:
    out = {"name": name, "python": python, "runs": {}, "errors": []}
    try:
        mig = subprocess.run([python, "-m", "airflow", "db", "migrate"], cwd=root, env=env,
                             capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as exc:
        out["errors"].append(f"airflow db migrate could not run: {exc}")
        return out
    if mig.returncode != 0:
        out["errors"].append(f"airflow db migrate failed: {mig.stderr.strip()[-500:]}")
        return out
    for dag_id, flags in plan:
        cmd = [python, str(REPLAY), dag_id, *flags, "--use-configured-db"]
        try:
            # replay_runs.py kills its run process when it is killed itself.
            proc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            out["errors"].append(f"{dag_id}: replay timed out after {timeout}s; later plan lines skipped")
            break
        except OSError as exc:
            out["errors"].append(f"{dag_id}: replay could not start: {exc}")
            break
        runs, summary = [], {}
        for line in proc.stdout.splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if "summary" in obj:
                summary = obj["summary"]
            else:
                runs.append(obj)
        out["runs"].setdefault(dag_id, []).extend(runs)  # a DAG may appear on several lines
        if summary.get("exit_code") in (1, 3) or not summary:
            msg = "; ".join(summary.get("errors", [])) or proc.stderr.strip()[-400:]
            imp = summary.get("import_errors")
            out["errors"].append(f"{dag_id}: replay exit {summary.get('exit_code', proc.returncode)}: "
                                 f"{msg}{' import_errors=' + json.dumps(imp)[:400] if imp else ''}")
    return out


def run_key(run: dict) -> str:
    return f"{run.get('kind')}@{run.get('run_after')}"


def keyed_runs(runs: list[dict]) -> dict[str, dict]:
    """Runs by kind@run_after; a repeated key (same rerun twice) gets a #2, #3... suffix."""
    out, seen = {}, {}
    for run in runs:
        key = run_key(run)
        seen[key] = seen.get(key, 0) + 1
        out[key if seen[key] == 1 else f"{key}#{seen[key]}"] = run
    return out


def compare_runs(before: dict, after: dict, legacy: bool) -> tuple[list[str], list[str]]:
    diffs, notes = [], []
    for dag_id in after["runs"]:
        b = keyed_runs(before["runs"].get(dag_id, []))
        a = keyed_runs(after["runs"][dag_id])
        for key in sorted(set(a) | set(b)):
            rb, ra = b.get(key), a.get(key)
            if rb is None or ra is None:
                msg = f"{dag_id} {key}: only in {'AFTER' if rb is None else 'BEFORE'}"
                if rb is None and legacy:  # emulated baseline could not run this DAG
                    notes.append(msg + " (emulated BEFORE did not run it)")
                else:
                    diffs.append(msg)
                continue
            if ra.get("state") not in ("success",):
                diffs.append(f"{dag_id} {key}: AFTER run {ra.get('state')}, failed={ra.get('failed_tasks')} "
                             f"{'; '.join(ra.get('errors', []))[:300]}")
            if rb.get("state") not in ("success",):
                notes.append(f"{dag_id} {key}: BEFORE run {rb.get('state')} (failed={rb.get('failed_tasks')}): "
                             "no baseline for this run's outputs")
            if rb.get("kind") == "manual":
                if legacy and rb.get("state") == "success":
                    notes.append(f"{dag_id} {key}: manual run uses 3.x semantics on both sides; "
                                 "no 2.x baseline")
                continue  # manual-run dates legitimately differ between 2.x and 3.x
            for field in ("logical_date", "data_interval_start", "data_interval_end"):
                if rb.get(field) != ra.get(field):
                    diffs.append(f"{dag_id} {key}: {field} BEFORE={rb.get(field)} AFTER={ra.get(field)}")
    return diffs, notes


def snapshot(root: Path, rels: list[str]) -> dict[str, Path]:
    files = {}
    for rel in rels:
        base = root / rel
        if base.is_file():
            files[rel] = base
            continue
        for path in sorted(base.rglob("*")) if base.is_dir() else []:
            if path.is_file():
                files[str(path.relative_to(root))] = path
    return files


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_files(before: Path, after: Path, rels: list[str], legacy: bool, notes: list[str]) -> list[str]:
    fb, fa = snapshot(before, rels), snapshot(after, rels)
    diffs = []
    for rel in sorted(set(fb) | set(fa)):
        if rel not in fa:
            diffs.append(f"missing in AFTER: {rel}")
        elif rel not in fb:
            if legacy:  # the emulated BEFORE run that would write it may have failed
                notes.append(f"extra in AFTER (no emulated baseline): {rel}")
            else:
                diffs.append(f"extra in AFTER: {rel}")
        elif digest(fb[rel]) != digest(fa[rel]):
            diffs.append(f"changed: {rel}")
            try:
                lines = list(difflib.unified_diff(fb[rel].read_text().splitlines(),
                                                  fa[rel].read_text().splitlines(),
                                                  "BEFORE", "AFTER", lineterm="", n=0))
                diffs.extend("    " + ln for ln in lines[2:2 + MAX_DIFF_LINES])
            except UnicodeDecodeError:
                pass
    return diffs


def main(argv=None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        before, after = Path(args.before).resolve(), Path(args.after).resolve()
        for root in (before, after):
            if not (root / "dags").is_dir():
                raise UsageError(f"{root} has no dags/ folder")
        if before == after:
            raise UsageError("--before and --after must be different copies")
        if not REPLAY.exists():
            raise UsageError(f"replay_runs.py not found next to this script ({REPLAY})")
        plan = read_plan(args.plan)
        extra = {}
        for pair in args.env:
            key, sep, value = pair.partition("=")
            if not sep:
                raise UsageError(f"--env expects KEY=VALUE, got {pair!r}")
            extra[key] = value
        outputs = args.outputs or ["output"]
        for root in (before, after):
            if root in before.parents or root in after.parents:
                raise UsageError("--before and --after must not contain each other")
            for rel in outputs:
                target = (root / rel).resolve()
                if target == root or root not in target.parents:
                    raise UsageError(f"--outputs {rel!r} must be a path inside the project copy")
    except (UsageError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if not args.keep_outputs:
        for root in (before, after):
            for rel in outputs:
                target = root / rel
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.is_file():
                    target.unlink()

    before_py = args.before_python or args.after_python
    jobs = (("BEFORE", before, before_py, args.legacy_before), ("AFTER", after, args.after_python, False))
    for name, root, py, legacy in jobs:
        print(f"== replaying {name} ({root}) with {py}{' + 2.x scheduler defaults' if legacy else ''}",
              flush=True)
    # The two sides are independent copies with their own metadata DBs: replay them in parallel.
    with ThreadPoolExecutor(max_workers=2) as pool:
        sides = list(pool.map(lambda j: replay_side(j[0], j[1], j[2], plan, side_env(j[1], extra, j[3]),
                                                    args.timeout), jobs))
    b, a = sides
    run_diffs, notes = compare_runs(b, a, args.legacy_before)
    file_diffs = compare_files(before, after, outputs, args.legacy_before, notes)
    errors = [f"{s['name']}: {e}" for s in sides for e in s["errors"]]

    for title, items in (("Replay errors", errors), ("Run differences", run_diffs),
                         ("Output differences", file_diffs), ("No baseline", notes)):
        if items:
            print(f"\n{title}:")
            for item in items:
                print(f"  {item}")
    for s in sides:
        print(f"\n{s['name']} runs:")
        for dag_id, runs in s["runs"].items():
            for r in runs:
                print(f"  {dag_id} {r.get('kind'):9} run_after={r.get('run_after')} "
                      f"logical={r.get('logical_date')} state={r.get('state')}")
    identical = not (errors or run_diffs or file_diffs)
    if identical and notes:
        verdict = (f"NO DIFFERENCES, BUT NOT PROVEN: {len(notes)} run(s)/file(s) have no baseline; "
                   "check them against the 2.x behaviour by hand")
    else:
        verdict = "IDENTICAL: same runs, same outputs" if identical else "DIFFERENT"
    print("\n" + verdict)
    print(json.dumps({"identical": identical, "errors": len(errors), "run_differences": len(run_diffs),
                      "output_differences": sum(1 for d in file_diffs if not d.startswith("    ")),
                      "no_baseline": len(notes)}))
    if not identical:
        return EXIT_DIFF
    return EXIT_UNPROVEN if notes else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
