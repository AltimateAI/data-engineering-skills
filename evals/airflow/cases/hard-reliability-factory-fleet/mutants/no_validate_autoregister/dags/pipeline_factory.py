"""Builds one DAG per pipeline config in configs/pipelines/*.yaml.

Each config names its team (looked up in the platform registry for owners and
retry defaults), a schedule (hour and day-of-week; the start minute is spread
over the hour so the warehouse does not get every pipeline at :00) and a list
of steps. Every step becomes a task that runs `run_step`.

Parsing rules this file keeps:
- the registry is read once per parse (with libyaml when available);
- a config that fails to load, build or validate is logged with its file
  name and skipped, so it only takes out its own DAG;
- every value that ends up in a DAG comes from the configs, never from the
  clock, the process (`hash()` is salted per process) or the set of other
  configs, so each DAG serializes the same way on every parse;
- when a worker parses the file to run one task, only that task's DAG is built;
- every task runs in the `warehouse` pool (pools.json) and critical pipelines
  outrank standard ones with absolute priority weights.
"""

from __future__ import annotations

import json
import logging
import zlib
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import yaml
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, get_parsing_context

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs" / "pipelines"
REGISTRY = PROJECT_ROOT / "configs" / "registry.yaml"
OUTPUT_DIR = PROJECT_ROOT / "output"
Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
WAREHOUSE_POOL = "warehouse"
PRIORITY = {"critical": 10, "standard": 1}


def run_step(pipeline: str, step: str, table: str, **context) -> str:
    """Stand-in for the warehouse call: records which step ran for which logical date."""
    logical_date = context.get("logical_date")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "pipeline": pipeline,
        "step": step,
        "table": table,
        "logical_date": logical_date.isoformat() if logical_date else None,
    }
    with open(OUTPUT_DIR / f"{pipeline}.jsonl", "a") as fh:
        fh.write(json.dumps(record) + "\n")
    print(f"{pipeline}.{step} -> {table}")
    return table


def load_yaml(path: Path) -> dict:
    with open(path) as fh:
        return yaml.load(fh, Loader=Loader)


@lru_cache(maxsize=1)
def registry() -> dict:
    return load_yaml(REGISTRY)


def start_minute(name: str) -> int:
    # Stable across processes (unlike hash()) and independent of other configs.
    return zlib.crc32(name.encode()) % 60


def build_dag(path: Path, cfg: dict) -> DAG:
    reg = registry()
    team = reg["teams"][cfg["team"]]
    sched = cfg["schedule"]
    minute = sched.get("minute", start_minute(cfg["name"]))
    owners = list(dict.fromkeys([*team["owners"], *cfg.get("owners", [])]))

    dag = DAG(
        dag_id=cfg["name"],
        description=cfg.get("description"),
        schedule=f"{minute} {sched['hour']} * * {sched.get('days', '*')}",
        start_date=datetime(2026, 1, 1),
        catchup=False,
        tags=[cfg["team"], "fleet"],
        # Registered through globals() only once fully built and validated:
        # with auto-registration a DAG that fails half-way would still load.
        doc_md=f"Generated from `{path.name}`. On-call: {team['oncall']} ({team['slack']}).",
        default_args={
            "owner": ",".join(owners),
            "retries": cfg.get("retries", team["default_retries"]),
            "retry_delay": timedelta(minutes=5),
            # Every step is a warehouse query: share the fleet-wide warehouse pool.
            "pool": WAREHOUSE_POOL,
            # Absolute weights: the scheduler compares these as-is, so a critical
            # task outranks every standard task whatever the size of either DAG
            # (the default "downstream" rule sums weights over downstream tasks).
            "priority_weight": PRIORITY[cfg.get("tier", "standard")],
            "weight_rule": "absolute",
        },
    )
    with dag:
        tasks = {}
        for step in cfg["steps"]:
            if step["table"] not in reg["datasets"]:
                raise ValueError(f"unknown table {step['table']!r}: register it in the platform catalog first")
            tasks[step["name"]] = PythonOperator(
                task_id=step["name"],
                python_callable=run_step,
                op_kwargs={"pipeline": cfg["name"], "step": step["name"], "table": step["table"]},
            )
        for step in cfg["steps"]:
            for upstream in step.get("depends_on", []):
                tasks[upstream] >> tasks[step["name"]]
    # Checks the DagBag would otherwise run later for the whole file
    # (an invalid cron expression, a dependency cycle), so they fail only this config.
    dag.check_cycle()
    return dag


def build_all() -> None:
    wanted = get_parsing_context().dag_id
    for path in sorted(CONFIG_DIR.glob("*.yaml")):
        try:
            cfg = load_yaml(path)
            if wanted and cfg.get("name") != wanted:
                continue
            dag = build_dag(path, cfg)
        except Exception:
            log.exception("Skipping pipeline config %s: it could not be built", path.name)
            continue
        globals()[dag.dag_id] = dag


build_all()
