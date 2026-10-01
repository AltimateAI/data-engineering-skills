#!/usr/bin/env python3
"""Compare two airflow_check.py --json run previews (BEFORE vs AFTER a migration).

Runs are matched per DAG by run_after (the wall-clock time the run fires). For
every matched run the chosen fields (default: logical_date, data_interval_start,
data_interval_end) must be identical, the set of fire times must be identical,
and catchup, timetable class and summary must be identical (allowing the Airflow
Dataset-to-Asset rename). Anything else is reported as a difference.

Stdlib only; it does not import Airflow.

A comparison only counts when both previews are complete: an import error on
either side, a scheduled DAG whose runs could not be previewed, a requested
--dag-id missing from both files, or no DAG at all is a failure, not a match.

Exit codes:
  0  every DAG present in both previews matches
  2  at least one difference, a DAG missing from one side, an import error or an
     unavailable preview in either file, or nothing to compare
  3  usage error (unreadable file, not airflow_check JSON, unknown field)
"""

from __future__ import annotations

import argparse
import json
import sys

FIELDS = ("logical_date", "data_interval_start", "data_interval_end")
MAX_DIFFS_PER_DAG = 20


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):  # exit 3 on bad arguments, not argparse's 2
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        sys.exit(3)


def _find_report(text: str) -> dict | None:
    """Return the airflow_check JSON object in text, skipping log lines around it
    (e.g. when stderr was redirected into the same file)."""
    decoder = json.JSONDecoder()
    pos = 0
    while True:
        start = text.find("{", pos)
        if start < 0:
            return None
        if start == 0 or text[start - 1] == "\n":
            try:
                obj, _ = decoder.raw_decode(text, start)
            except ValueError:
                obj = None
            if isinstance(obj, dict) and isinstance(obj.get("dags"), list):
                return obj
        pos = start + 1


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise UsageError(f"cannot read {path}: {exc}") from exc
    data = _find_report(text)
    if data is None:
        raise UsageError(f"{path} does not contain airflow_check.py --json output (no 'dags' list); "
                         "re-run airflow_check.py with --json and 2>/dev/null")
    return data


UNSCHEDULED = ("NullTimetable", "AssetTriggeredTimetable", "DatasetTriggeredTimetable",
               "DatasetTriggeredSchedule")


def timetable_value(value):
    """Normalize only the known 2.x Dataset -> 3.x Asset timetable renames."""
    aliases = {"DatasetTriggeredSchedule": "AssetTriggeredTimetable",
               "DatasetTriggeredTimetable": "AssetTriggeredTimetable",
               "DatasetOrTimeSchedule": "AssetOrTimeSchedule", "Dataset": "Asset"}
    if value in aliases:
        return aliases[value]
    if isinstance(value, str) and value.startswith("Dataset or "):
        return "Asset or " + value[len("Dataset or "):]
    return value


def index(data: dict, only: set[str], path: str) -> dict[str, dict]:
    out = {}
    for d in data["dags"]:
        if not isinstance(d, dict) or not isinstance(d.get("dag_id"), str):
            raise UsageError(f"{path}: a 'dags' entry has no dag_id; not airflow_check.py output")
        if not only or d["dag_id"] in only:
            out[d["dag_id"]] = d
    return out


def preview_missing(dag: dict) -> bool:
    """True when a scheduled DAG has no previewed runs (preview failed or had no start_date)."""
    tt = dag.get("timetable") or ""
    scheduled = tt and tt not in UNSCHEDULED
    return bool(scheduled) and not dag.get("next_runs")


def compare_dag(before: dict, after: dict, fields: tuple[str, ...]) -> dict:
    diffs: list[dict] = []
    for side, dag in (("before", before), ("after", after)):
        if preview_missing(dag):
            reason = next((w for w in dag.get("warnings", []) if "preview" in w), "no runs previewed")
            diffs.append({"field": "preview", side: f"unavailable: {reason[:200]}"})
    if before.get("catchup") != after.get("catchup"):
        diffs.append({"field": "catchup", "before": before.get("catchup"), "after": after.get("catchup")})
    for field in ("timetable", "timetable_summary"):
        if timetable_value(before.get(field)) != timetable_value(after.get(field)):
            diffs.append({"field": field, "before": before.get(field), "after": after.get(field)})
    b_runs = {r["run_after"]: r for r in before.get("next_runs", [])}
    a_runs = {r["run_after"]: r for r in after.get("next_runs", [])}
    for ra in sorted(set(b_runs) | set(a_runs)):
        if ra not in a_runs:
            diffs.append({"run_after": ra, "field": "run", "before": "present", "after": "missing"})
            continue
        if ra not in b_runs:
            diffs.append({"run_after": ra, "field": "run", "before": "missing", "after": "present"})
            continue
        for f in fields:
            if b_runs[ra].get(f) != a_runs[ra].get(f):
                diffs.append({"run_after": ra, "field": f,
                              "before": b_runs[ra].get(f), "after": a_runs[ra].get(f)})
    if not b_runs and not a_runs:
        note = "no runs previewed on either side (manual/asset schedule or preview failed)"
    else:
        note = ""
    return {
        "dag_id": before["dag_id"],
        "status": "match" if not diffs else "differs",
        "timetable": {"before": before.get("timetable"), "after": after.get("timetable")},
        "runs_compared": len(set(b_runs) & set(a_runs)),
        "diffs": diffs[:MAX_DIFFS_PER_DAG],
        "diffs_truncated": max(0, len(diffs) - MAX_DIFFS_PER_DAG),
        "note": note,
    }


def main(argv: list[str] | None = None) -> int:
    p = Parser(
        description="Compare BEFORE/AFTER airflow_check.py --json previews run by run.",
        epilog="Exit codes: 0 all match, 2 differences, 3 usage error.",
    )
    p.add_argument("before", help="JSON from airflow_check.py --json on the pre-migration code")
    p.add_argument("after", help="JSON from airflow_check.py --json on the migrated code")
    p.add_argument("--dag-id", action="append", default=[], help="only compare this DAG (repeatable)")
    p.add_argument("--fields", default=",".join(FIELDS),
                   help=f"comma-separated run fields to compare (default: {','.join(FIELDS)})")
    args = p.parse_args(argv)

    fields = tuple(f.strip() for f in args.fields.split(",") if f.strip())
    allowed = set(FIELDS) | {"run_after"}
    try:
        bad = [f for f in fields if f not in allowed]
        if bad or not fields:
            raise UsageError(f"unknown --fields {bad or fields}; allowed: {sorted(allowed)}")
        before = load(args.before)
        after = load(args.after)
    except UsageError as exc:
        print(json.dumps({"error": str(exc), "exit_code": 3}))
        return 3

    only = set(args.dag_id)
    try:
        b_idx, a_idx = index(before, only, args.before), index(after, only, args.after)
    except UsageError as exc:
        print(json.dumps({"error": str(exc), "exit_code": 3}))
        return 3
    results = []
    for dag_id in sorted(set(b_idx) | set(a_idx) | only):
        if dag_id not in a_idx and dag_id not in b_idx:
            results.append({"dag_id": dag_id, "status": "missing_both", "diffs": []})
        elif dag_id not in a_idx:
            results.append({"dag_id": dag_id, "status": "missing_after", "diffs": []})
        elif dag_id not in b_idx:
            results.append({"dag_id": dag_id, "status": "missing_before", "diffs": []})
        else:
            results.append(compare_dag(b_idx[dag_id], a_idx[dag_id], fields))

    differing = [r["dag_id"] for r in results if r["status"] != "match"]
    import_errors = {"before": len(before.get("import_errors") or []),
                     "after": len(after.get("import_errors") or [])}
    problems = []
    if any(import_errors.values()):
        problems.append("import errors in a preview: DAGs in failing files were not compared; "
                        "fix them and capture again")
    if not results:
        problems.append("no DAGs to compare")
    code = 2 if differing or problems else 0
    out = {
        "fields": list(fields),
        "dags": results,
        "import_errors": import_errors,
        "summary": {"dags": len(results), "match": len(results) - len(differing),
                    "differs": differing, "problems": problems},
        "exit_code": code,
    }
    print(json.dumps(out, indent=1))
    return code


if __name__ == "__main__":
    sys.exit(main())
