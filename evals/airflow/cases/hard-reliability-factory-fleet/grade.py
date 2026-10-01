"""Grader for hard-reliability-factory-fleet.

The fixture factory builds 140 DAGs from configs/pipelines/*.yaml. It re-reads
the 0.5 MB platform registry with the pure-Python YAML loader for every
pipeline (the file takes over a minute to parse, so the dag-processor kills it
at the 30 s import timeout), lets one bad config raise out of the module (every
DAG disappears), and puts per-process values into the DAGs: `hash(name) % 60`
as the start minute (salted per process), a `set` joined into `owner`, and the
parse time in `doc_md`. Workers parse all 140 DAGs to run one task.

The grader parses the fixed repo the way the dag-processor and workers do and
checks each requirement from the prompt by behaviour:
- every pipeline config still yields its DAG with the same tasks, edges,
  owners, retries and run times (cron fire times compared with a reference
  timetable built from the config);
- start minutes stay spread over the hour; explicit `minute:` is honoured;
- the file parses in <= PARSE_BUDGET_S (median of three parses);
- three fresh parses (different PYTHONHASHSEED, TZ and a clock moved ahead)
  give every DAG the same Airflow `dag_hash`;
- broken configs (syntax error, empty file, unknown team, unknown dependency,
  invalid day-of-week, unregistered table) only remove their own DAG, are named
  in the parse output, and leave every other DAG's hash unchanged; adding and
  removing a config does not change any other DAG either;
- with the worker parsing context set to one dag_id, only that DAG is built,
  and it is the same DAG as in a full parse;
- `airflow dags test` of two pipelines runs every step once, in dependency order.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import yaml

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("EVAL_HARNESS_DIR", str(CASE_DIR.parents[2] / "harness")))
import grading as g  # noqa: E402

PARSE_BUDGET_S = 5.0
CLOCK_SHIFT_S = str(3 * 86400 + 7 * 3600)
PARSE_SCENARIOS = [("1", "UTC", "0"), ("2", "Pacific/Kiritimati", "0"), ("3", "Etc/GMT+12", CLOCK_SHIFT_S)]
# Pipelines executed with `airflow dags test` (one linear, one with a skip edge).
RUN_PIPELINES = ("billing_carriers", "billing_promotions")
# Pipelines parsed under a worker parsing context.
CONTEXT_PIPELINES = ("finance_payouts", "support_payroll")
MIN_DISTINCT_MINUTES = 30
WAREHOUSE_POOL = "warehouse"
WAREHOUSE_SLOTS = 16
BIG_STEPS = 400
MAX_PER_MINUTE = 8

BROKEN = {
    "aa_unknown_team.yaml": {"name": "aa_unknown_team", "team": "astronomy",
                             "schedule": {"hour": 2}, "steps": [{"name": "extract", "table": "billing.raw_orders_00"}]},
    "mm_bad_dependency.yaml": {"name": "mm_bad_dependency", "team": "billing", "schedule": {"hour": 2},
                               "steps": [{"name": "extract", "table": "billing.raw_orders_00"},
                                         {"name": "publish", "table": "billing.mart_orders_00",
                                          "depends_on": ["transform"]}]},
    "mm_bad_days.yaml": {"name": "mm_bad_days", "team": "risk", "schedule": {"hour": 2, "days": "funday"},
                         "steps": [{"name": "extract", "table": "risk.raw_orders_00"}]},
    "mm_cycle.yaml": {"name": "mm_cycle", "team": "supply", "schedule": {"hour": 3},
                      "steps": [{"name": "extract", "table": "supply.raw_orders_00", "depends_on": ["publish"]},
                                {"name": "publish", "table": "supply.mart_orders_00", "depends_on": ["extract"]}]},
    "mm_duplicate_step.yaml": {"name": "mm_duplicate_step", "team": "people", "schedule": {"hour": 3},
                               "steps": [{"name": "extract", "table": "people.raw_orders_00"},
                                         {"name": "extract", "table": "people.raw_orders_00"},
                                         {"name": "publish", "table": "people.mart_orders_00",
                                          "depends_on": ["extract"]}]},
    "mm_unregistered_table.yaml": {"name": "mm_unregistered_table", "team": "search", "schedule": {"hour": 2},
                                   "steps": [{"name": "extract", "table": "search.raw_does_not_exist_00"}]},
}
BROKEN_TEXT = {
    "zz_broken_syntax.yaml": "name: zz_broken_syntax\nteam: billing\nschedule:\n  hour: 2\n steps:\n  - name: extract\n",
    "nn_empty.yaml": "",
}
NEW_CONFIG = {"name": "zz_new_pipeline", "team": "growth", "schedule": {"hour": 5},
              "steps": [{"name": "extract", "table": "growth.raw_orders_00"},
                        {"name": "publish", "table": "growth.mart_orders_00", "depends_on": ["extract"]}]}
# Grader-written configs carry every field the fleet's configs have (all 140 set
# `tier` and `description`), so a factory that requires them is not penalised and
# each broken config has exactly the one defect it is named after.
for _cfg in [*BROKEN.values(), NEW_CONFIG]:
    _cfg.setdefault("tier", "standard")
    _cfg.setdefault("description", f"{_cfg['name']} pipeline")

PARSE_PROBE = r"""
import json, os, time
import datetime as _dtmod
import pendulum, yaml  # noqa: F401
import airflow.sdk  # noqa: F401
import airflow.providers.standard.operators.python  # noqa: F401
from airflow.dag_processing.dagbag import DagBag  # noqa: F401
from airflow.models.serialized_dag import SerializedDagModel
from airflow.serialization.serialized_objects import DagSerialization
from airflow.timetables.trigger import CronTriggerTimetable  # noqa: F401

_shift = _dtmod.timedelta(seconds=float(os.environ.get("EVAL_CLOCK_SHIFT_S", "0")))
_real_dt, _real_date = _dtmod.datetime, _dtmod.date
if _shift:
    class _Meta(type):
        def __instancecheck__(cls, obj):
            return isinstance(obj, cls._real)

        def __subclasscheck__(cls, sub):
            return issubclass(sub, cls._real)

    class _ShiftedDatetime(_real_dt, metaclass=_Meta):
        _real = _real_dt

        def __new__(cls, *args, **kwargs):
            return _real_dt(*args, **kwargs)

        @classmethod
        def now(cls, tz=None):
            return _real_dt.now(tz) + _shift

        @classmethod
        def utcnow(cls):
            return _real_dt.utcnow() + _shift

        @classmethod
        def today(cls):
            return _real_dt.today() + _shift

    class _ShiftedDate(_real_date, metaclass=_Meta):
        _real = _real_date

        def __new__(cls, *args, **kwargs):
            return _real_date(*args, **kwargs)

        @classmethod
        def today(cls):
            return (_real_dt.now() + _shift).date()

    _dtmod.datetime, _dtmod.date = _ShiftedDatetime, _ShiftedDate
try:
    bag = dagbag()
finally:
    _dtmod.datetime, _dtmod.date = _real_dt, _real_date

def task_weights(dag):
    # The priority the scheduler stores on each task instance: the serialized
    # (scheduler-side) task's weight rule applied to a task instance.
    import uuid
    from airflow.models.taskinstance import TaskInstance
    sdag = DagSerialization.from_dict(DagSerialization.to_dict(dag))
    ws = [t.weight_rule.get_weight(TaskInstance(task=t, run_id="probe", map_index=-1, dag_version_id=uuid.uuid4()))
          for t in sdag.tasks]
    return [min(ws), max(ws)]


WANT_DETAILS = set(json.loads(os.environ.get("EVAL_DETAIL_DAGS", "[]")))
out = {}
for dag_id, dag in bag.dags.items():
    entry = {"hash": SerializedDagModel.hash(DagSerialization.to_dict(dag))}
    if WANT_DETAILS == {"*"} or dag_id in WANT_DETAILS:
        runs = []
        try:
            runs = [r["run_after"] for r in scheduled_intervals(dag, "2030-01-06T00:00:00+00:00", n=8)]
        except Exception as exc:
            runs = [f"error: {exc!r}"]
        entry.update({
            "tasks": sorted(t.task_id for t in dag.tasks),
            "deps": sorted([t.task_id, d] for t in dag.tasks for d in t.downstream_task_ids),
            "owners": sorted(o.strip() for t in dag.tasks[:1] for o in str(t.owner).split(",")),
            "retries": sorted({t.retries for t in dag.tasks}),
            "pools": sorted({str(t.pool) for t in dag.tasks}),
            "prio": task_weights(dag),
            "runs": runs,
        })
    out[dag_id] = entry
folder = os.environ["AIRFLOW__CORE__DAGS_FOLDER"]
RESULT = {"dags": out,
          "import_errors": {os.path.basename(k): v[-600:] for k, v in bag.import_errors.items()},
          "warnings": [str(w)[:300] for ws in (getattr(bag, "captured_warnings", None) or {}).values() for w in ws],
          "parse_s": max([s.duration.total_seconds() for s in bag.dagbag_stats] or [None])}
"""

EXPECTED_RUNS_PROBE = r"""
import json, os
from airflow.timetables.trigger import CronTriggerTimetable
specs = json.loads(os.environ["EVAL_SPECS"])

class _D:  # minimal stand-in so scheduled_intervals() can walk a bare timetable
    def __init__(self, tt):
        self.timetable = tt
        self.start_date = None
        self.end_date = None
        self.catchup = True

RESULT = {}
for name, expr in specs.items():
    RESULT[name] = [r["run_after"] for r in scheduled_intervals(_D(CronTriggerTimetable(expr, timezone="UTC")),
                                                                "2030-01-06T00:00:00+00:00", n=8)]
"""


def pristine_configs() -> dict[str, dict]:
    out = {}
    for path in sorted((CASE_DIR / "fixture" / "configs" / "pipelines").glob("*.yaml")):
        cfg = yaml.safe_load(path.read_text())
        out[cfg["name"]] = cfg
    return out


def registry() -> dict:
    return yaml.load((CASE_DIR / "fixture" / "configs" / "registry.yaml").read_text(), Loader=yaml.CSafeLoader)


def expected_shape(cfg: dict, reg: dict) -> dict:
    team = reg["teams"][cfg["team"]]
    return {
        "tasks": sorted(s["name"] for s in cfg["steps"]),
        "deps": sorted([u, s["name"]] for s in cfg["steps"] for u in s.get("depends_on", [])),
        "owners": sorted(set(team["owners"]) | set(cfg.get("owners", []))),
        "retries": [cfg.get("retries", team["default_retries"])],
    }


def parse(py: str, ws: Path, details=(), extra: dict | None = None, seed="1", tz="UTC", shift="0", timeout=400):
    env = g.airflow_env(ws, extra={"PYTHONHASHSEED": seed, "TZ": tz, "EVAL_CLOCK_SHIFT_S": shift,
                                   "EVAL_DETAIL_DAGS": json.dumps(list(details)), **(extra or {})})
    res, proc = g.probe_json(py, PARSE_PROBE, ws, env=env, timeout=timeout)
    if not isinstance(res, dict):
        return {"error": proc.tail(25)}, proc.output
    return res, proc.output


def check_shapes(py: str, ws: Path, full: dict, configs: dict, reg: dict, grader: g.Grader) -> None:
    dags = full["dags"]
    bad = []
    for name, cfg in configs.items():
        got = dags.get(name)
        if got is None:
            continue
        want = expected_shape(cfg, reg)
        diffs = {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v}
        if diffs:
            bad.append(f"{name}: {diffs}")
    grader.primary("each DAG keeps its config's tasks, dependencies, owners and retries", not bad,
                   "; ".join(bad[:5]) + (f" (+{len(bad) - 5} more)" if len(bad) > 5 else ""))

    # Fire times: compare against a reference timetable built from the config.
    explicit = {n: c["schedule"]["minute"] for n, c in configs.items() if "minute" in c["schedule"]}
    specs, minutes, problems = {}, {}, []
    for name, cfg in configs.items():
        runs = dags.get(name, {}).get("runs") or []
        if not runs or any(str(r).startswith("error") for r in runs):
            problems.append(f"{name}: no schedule ({runs[:1]})")
            continue
        minute = int(runs[0][14:16])
        minutes[name] = minute
        specs[name] = f"{explicit.get(name, minute)} {cfg['schedule']['hour']} * * {cfg['schedule'].get('days', '*')}"
    env = g.airflow_env(ws, extra={"EVAL_SPECS": json.dumps(specs)})
    expected, proc = g.probe_json(py, EXPECTED_RUNS_PROBE, ws, env=env, timeout=300)
    if expected is None:
        grader.primary("each DAG runs at its configured hour/days (and explicit minute)", False, proc.tail(10))
    else:
        for name in specs:
            if dags[name]["runs"] != expected[name]:
                problems.append(f"{name}: runs {dags[name]['runs'][:3]} expected {expected[name][:3]} "
                                f"(spec {specs[name]})")
        grader.primary("each DAG runs at its configured hour/days (and explicit minute)", not problems,
                       "; ".join(problems[:5]) + (f" (+{len(problems) - 5} more)" if len(problems) > 5 else ""))
    spread = [m for n, m in minutes.items() if n not in explicit]
    counts = {m: spread.count(m) for m in set(spread)}
    ok = len(counts) >= MIN_DISTINCT_MINUTES and max(counts.values() or [0]) <= MAX_PER_MINUTE
    grader.primary("start minutes stay spread over the hour", ok,
                   f"{len(spread)} pipelines without an explicit minute use {len(counts)} distinct minutes "
                   f"(need >= {MIN_DISTINCT_MINUTES}); busiest minute has {max(counts.values() or [0])} "
                   f"(max {MAX_PER_MINUTE})")


def check_isolation(py: str, ws: Path, configs: dict, grader: g.Grader) -> None:
    # Work on a copy; DAG hashes include the file location, so the baseline is
    # parsed from the same copy before any config is touched.
    copy = g.copy_workspace(ws)
    try:
        pdir = copy / "configs" / "pipelines"
        if not pdir.is_dir():
            grader.primary("broken configs only take out their own DAG", False, "configs/pipelines is missing")
            return
        base, _ = parse(py, copy)
        if "error" in base:
            grader.primary("broken configs only take out their own DAG", False, f"probe failed: {base['error']}")
            return
        base_hashes = {n: d["hash"] for n, d in base["dags"].items()}
        for fname, cfg in BROKEN.items():
            (pdir / fname).write_text(yaml.safe_dump(cfg, sort_keys=False))
        for fname, text in BROKEN_TEXT.items():
            (pdir / fname).write_text(text)
        res, output = parse(py, copy)
        if "error" in res:
            grader.primary("broken configs only take out their own DAG", False, f"probe failed: {res['error']}")
            return
        dags = res["dags"]
        missing = sorted(set(configs) - set(dags))
        changed = sorted(n for n in configs if n in dags and dags[n]["hash"] != base_hashes.get(n))
        leaked = sorted(set(dags) & {c["name"] for c in BROKEN.values()})
        ok = not missing and not changed and not leaked
        grader.primary("broken configs only take out their own DAG (others load unchanged, no partial DAGs)", ok,
                       f"missing {len(missing)} DAGs {missing[:5]}; changed hashes {changed[:5]}; "
                       f"half-built broken DAGs loaded {leaked}; import errors "
                       f"{ {k: v.strip().splitlines()[-1][:160] for k, v in res['import_errors'].items()} }")
        haystack = output + "\n".join(res.get("warnings", []))
        unnamed = sorted(f for f in [*BROKEN, *BROKEN_TEXT] if f not in haystack)
        grader.primary("each broken config is reported by file name in the parse output", not unnamed,
                       f"not mentioned: {unnamed}")

        # Adding a pipeline and removing another leaves every other DAG alone.
        for fname in [*BROKEN, *BROKEN_TEXT]:
            (pdir / fname).unlink()
        removed = sorted(configs)[0]
        for path in pdir.glob("*.yaml"):
            if yaml.safe_load(path.read_text()).get("name") == removed:
                path.unlink()
        (pdir / "zz_new_pipeline.yaml").write_text(yaml.safe_dump(NEW_CONFIG, sort_keys=False))
        res, _ = parse(py, copy)
        if "error" in res:
            grader.primary("adding/removing a config leaves every other DAG unchanged", False, res["error"])
            return
        dags = res["dags"]
        changed = sorted(n for n in configs if n != removed and dags.get(n, {}).get("hash") != base_hashes.get(n))
        ok = not changed and "zz_new_pipeline" in dags and removed not in dags
        grader.primary("adding/removing a config leaves every other DAG unchanged", ok,
                       f"changed or missing: {changed[:6]} ({len(changed)}); new present="
                       f"{'zz_new_pipeline' in dags}; removed {removed} gone={removed not in dags}")
    finally:
        shutil.rmtree(copy.parent, ignore_errors=True)


def big_standard_config() -> dict:
    steps = [{"name": "extract", "table": "growth.raw_orders_00"}]
    for i in range(1, BIG_STEPS):
        steps.append({"name": f"step_{i:03d}", "table": "growth.int_orders_00", "depends_on": [steps[-1]["name"]]})
    return {"name": "zz_big_standard", "team": "growth", "tier": "standard", "description": "Big standard pipeline",
            "schedule": {"hour": 1}, "steps": steps}


TINY_CRITICAL = {"name": "zz_tiny_critical", "team": "finance", "tier": "critical",
                 "description": "Tiny critical pipeline", "schedule": {"hour": 1},
                 "steps": [{"name": "extract", "table": "finance.raw_orders_00"}]}


def check_concurrency(py: str, ws: Path, configs: dict, grader: g.Grader) -> None:
    # Pool definition: the deploy runs `airflow pools import pools.json`.
    env = g.airflow_env(ws)
    db = g.ensure_db(py, env)
    pools_file = ws / "pools.json"
    slots, detail = None, ""
    if not pools_file.is_file():
        detail = "pools.json is missing"
    elif not db.ok:
        detail = db.tail(10)
    else:
        imp = g.run_cmd([str(Path(py).parent / "airflow"), "pools", "import", str(pools_file)], env=env, cwd=ws)
        res, proc = g.probe_json(py, """
            from airflow.models.pool import Pool
            from airflow.utils.session import create_session
            with create_session() as s:
                RESULT = {p.pool: p.slots for p in s.query(Pool).all()}
        """, ws, env=env)
        slots = (res or {}).get(WAREHOUSE_POOL)
        detail = f"pools after import: {res}" + ("" if imp.ok else f"; import failed: {imp.tail(5)}")
    grader.primary(f"pools.json defines pool {WAREHOUSE_POOL!r} with {WAREHOUSE_SLOTS} slots",
                   slots == WAREHOUSE_SLOTS, detail)

    # Every fleet task runs in the warehouse pool, and critical outranks standard
    # even with a very long standard pipeline and a one-step critical one added.
    copy = g.copy_workspace(ws)
    try:
        pdir = copy / "configs" / "pipelines"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "zz_big_standard.yaml").write_text(yaml.safe_dump(big_standard_config(), sort_keys=False))
        (pdir / "zz_tiny_critical.yaml").write_text(yaml.safe_dump(TINY_CRITICAL, sort_keys=False))
        res, _ = parse(py, copy, details=("*",))
        if "error" in res:
            grader.primary("every fleet task runs in the warehouse pool", False, res["error"])
            grader.primary("critical tasks always outrank standard tasks", False, res["error"])
            return
        dags = res["dags"]
        tiers = {n: c.get("tier", "standard") for n, c in configs.items()}
        tiers.update({"zz_big_standard": "standard", "zz_tiny_critical": "critical"})
        absent = sorted(n for n in tiers if n not in dags)
        wrong_pool = sorted(n for n in tiers if n in dags and dags[n].get("pools") != [WAREHOUSE_POOL])
        grader.primary("every fleet task runs in the warehouse pool", not wrong_pool and not absent,
                       f"DAGs with other pools: {[(n, dags[n].get('pools')) for n in wrong_pool[:4]]}; "
                       f"missing DAGs: {absent[:4]}")
        crit = [dags[n]["prio"][0] for n, t in tiers.items() if t == "critical" and n in dags]
        std = [dags[n]["prio"][1] for n, t in tiers.items() if t == "standard" and n in dags]
        ok = bool(crit) and bool(std) and not absent and min(crit) > max(std)
        lowest = min(((dags[n]["prio"][0], n) for n, t in tiers.items() if t == "critical" and n in dags), default=None)
        highest = max(((dags[n]["prio"][1], n) for n, t in tiers.items() if t == "standard" and n in dags), default=None)
        grader.primary("critical tasks always outrank standard tasks (scheduler priority weight)", ok,
                       f"lowest critical task weight {lowest}; highest standard task weight {highest} "
                       f"(with a {BIG_STEPS}-step standard pipeline and a 1-step critical pipeline added)")
    finally:
        shutil.rmtree(copy.parent, ignore_errors=True)


def check_parsing_context(py: str, ws: Path, base_hashes: dict, grader: g.Grader) -> None:
    problems = []
    for dag_id in CONTEXT_PIPELINES:
        res, _ = parse(py, ws, extra={"_AIRFLOW_PARSING_CONTEXT_DAG_ID": dag_id,
                                      "_AIRFLOW_PARSING_CONTEXT_TASK_ID": "extract"})
        if "error" in res:
            problems.append(f"{dag_id}: probe failed {res['error'][-300:]}")
            continue
        built = sorted(res["dags"])
        if built != [dag_id]:
            problems.append(f"{dag_id}: built {len(built)} DAGs ({built[:3]}...)")
        elif res["dags"][dag_id]["hash"] != base_hashes.get(dag_id):
            problems.append(f"{dag_id}: differs from the DAG built in a full parse")
    grader.primary("a worker parsing for one task builds only that task's DAG", not problems, "; ".join(problems))


def check_runs(py: str, ws: Path, configs: dict, grader: g.Grader) -> None:
    for dag_id in RUN_PIPELINES:
        shutil.rmtree(ws / "output", ignore_errors=True)
        run = g.run_dags_test(py, ws, dag_id, logical_date="2026-03-02T06:00:00+00:00",
                              env=g.airflow_env(ws), timeout=600)
        detail = "" if run.ok else f"failed tasks={run.failed_tasks()}\n{run.log[-2500:]}"
        problems = []
        out = ws / "output" / f"{dag_id}.jsonl"
        if run.ok:
            rows = [json.loads(line) for line in out.read_text().splitlines()] if out.exists() else []
            steps = [r.get("step") for r in rows]
            cfg = configs[dag_id]
            want = sorted(s["name"] for s in cfg["steps"])
            if sorted(steps) != want:
                problems.append(f"steps run {steps}, expected each of {want} once")
            pos = {s: i for i, s in enumerate(steps)}
            for s in cfg["steps"]:
                for u in s.get("depends_on", []):
                    if u in pos and s["name"] in pos and pos[u] > pos[s["name"]]:
                        problems.append(f"{s['name']} ran before {u}")
            if any(not str(r.get("logical_date", "")).startswith("2026-03-02") for r in rows):
                problems.append(f"logical dates {sorted({r.get('logical_date') for r in rows})}")
            detail = "; ".join(problems) or f"{len(rows)} steps"
        grader.primary(f"airflow dags test {dag_id} runs every step once in order", run.ok and not problems, detail)


def main() -> None:
    args = g.parse_args()
    ws, py = args.workspace, sys.executable
    grader = g.Grader()
    events = g.load_events(args.events)
    configs = pristine_configs()
    reg = registry()

    imp = g.import_dags(py, ws, env=g.airflow_env(ws), timeout=400)
    grader.primary("DAG files import cleanly", imp["ok"] and not imp["import_errors"],
                   imp["probe_error"] or "; ".join(f"{k}: {v.strip().splitlines()[-1]}"
                                                   for k, v in imp["import_errors"].items()))
    missing = sorted(set(configs) - set(imp["dags"]))
    grader.primary("every pipeline config yields its DAG", not missing,
                   f"{len(missing)} of {len(configs)} missing: {missing[:6]}")

    parses = []
    for i, (seed, tz, shift) in enumerate(PARSE_SCENARIOS):
        res, _ = parse(py, ws, details=("*",) if i == 0 else (), seed=seed, tz=tz, shift=shift)
        parses.append(res)
    errors = [p["error"] for p in parses if "error" in p]
    if errors or missing:
        grader.primary("every parse serializes each DAG the same way", False,
                       f"probe errors: {[e[-400:] for e in errors]}" if errors else "DAGs missing")
        times = [p.get("parse_s") for p in parses]
        grader.primary(f"factory parses in <= {PARSE_BUDGET_S}s", False, f"parse seconds={times}")
    else:
        unstable = sorted(n for n in configs if len({p["dags"].get(n, {}).get("hash") for p in parses}) > 1)
        grader.primary("every parse serializes each DAG the same way", not unstable,
                       f"{len(unstable)} DAGs change between parses: {unstable[:6]}")
        times = [p.get("parse_s") for p in parses]
        # Median of the three parses, so one parse slowed by a busy grading machine does not decide it.
        median = sorted(t if t is not None else float("inf") for t in times)[1]
        grader.primary(f"factory parses in <= {PARSE_BUDGET_S}s", median <= PARSE_BUDGET_S,
                       f"parse seconds={times} (median {median})")
        full = parses[0]
        base_hashes = {n: d["hash"] for n, d in full["dags"].items()}
        check_shapes(py, ws, full, configs, reg, grader)
        check_isolation(py, ws, configs, grader)
        check_parsing_context(py, ws, base_hashes, grader)
        check_concurrency(py, ws, configs, grader)
    check_runs(py, ws, configs, grader)

    g.standard_secondary_checks(grader, py, ws, events, import_result=imp)
    grader.write(args.out)


if __name__ == "__main__":
    main()
