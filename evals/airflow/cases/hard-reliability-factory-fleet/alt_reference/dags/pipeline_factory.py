"""Builds one DAG per pipeline config in configs/pipelines/*.yaml.

Alternative fix: every config is validated in full before any DAG object is
created (team, steps, dependencies, registered tables, cron expression), so
nothing can fail half-way through building a DAG. Problems are reported as
warnings that name the config file. The registry is parsed once per process.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, get_parsing_context
from croniter import croniter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs" / "pipelines"
REGISTRY = PROJECT_ROOT / "configs" / "registry.yaml"
OUTPUT_DIR = PROJECT_ROOT / "output"


class ConfigError(Exception):
    pass


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


def spread_minute(name: str) -> int:
    return int(hashlib.sha256(name.encode()).hexdigest(), 16) % 60


def validated(cfg, registry: dict) -> dict:
    if not isinstance(cfg, dict):
        raise ConfigError("config is empty or not a mapping")
    for key in ("name", "team", "schedule", "steps"):
        if key not in cfg:
            raise ConfigError(f"missing {key!r}")
    if cfg["team"] not in registry["teams"]:
        raise ConfigError(f"unknown team {cfg['team']!r}")
    names = [s["name"] for s in cfg["steps"]]
    if len(set(names)) != len(names):
        raise ConfigError("duplicate step names")
    deps = {s["name"]: list(s.get("depends_on", [])) for s in cfg["steps"]}
    done: set[str] = set()

    def visit(node: str, path: tuple[str, ...]) -> None:
        if node in path:
            raise ConfigError(f"dependency cycle through {node!r}")
        if node in done:
            return
        for up in deps.get(node, []):
            visit(up, path + (node,))
        done.add(node)

    for n in names:
        visit(n, ())
    for step in cfg["steps"]:
        if step["table"] not in registry["datasets"]:
            raise ConfigError(f"table {step['table']!r} is not registered")
        for up in step.get("depends_on", []):
            if up not in names:
                raise ConfigError(f"step {step['name']!r} depends on unknown step {up!r}")
    sched = cfg["schedule"]
    minute = sched.get("minute", spread_minute(cfg["name"]))
    cron = f"{minute} {sched['hour']} * * {sched.get('days', '*')}"
    if not croniter.is_valid(cron):
        raise ConfigError(f"invalid schedule {cron!r}")
    return {**cfg, "cron": cron}


def build(cfg: dict, registry: dict, filename: str) -> DAG:
    team = registry["teams"][cfg["team"]]
    owners = sorted(set(team["owners"]) | set(cfg.get("owners", [])))
    with DAG(
        dag_id=cfg["name"],
        description=cfg.get("description"),
        schedule=cfg["cron"],
        start_date=datetime(2026, 1, 1),
        catchup=False,
        tags=[cfg["team"], "fleet"],
        doc_md=f"Generated from `{filename}`. On-call: {team['oncall']} ({team['slack']}).",
        default_args={
            "owner": ",".join(owners),
            "retries": cfg.get("retries", team["default_retries"]),
            "retry_delay": timedelta(minutes=5),
            "pool": "warehouse",
        },
    ) as dag:
        tasks = {
            s["name"]: PythonOperator(
                task_id=s["name"],
                python_callable=run_step,
                op_kwargs={"pipeline": cfg["name"], "step": s["name"], "table": s["table"]},
                priority_weight=1000 if cfg.get("tier") == "critical" else 0,
                weight_rule="absolute",
            )
            for s in cfg["steps"]
        }
        for s in cfg["steps"]:
            for up in s.get("depends_on", []):
                tasks[up] >> tasks[s["name"]]
    return dag


def main() -> None:
    wanted = get_parsing_context().dag_id
    paths = sorted(CONFIG_DIR.glob("*.yaml"))
    if wanted and (CONFIG_DIR / f"{wanted}.yaml").is_file():
        paths = [CONFIG_DIR / f"{wanted}.yaml"]
    registry = None
    for path in paths:
        try:
            raw = yaml.safe_load(path.read_text())
            if wanted and isinstance(raw, dict) and raw.get("name") != wanted:
                continue
            registry = registry or yaml.safe_load(REGISTRY.read_text())
            build(validated(raw, registry), registry, path.name)
        except Exception as exc:  # one bad config must not hide the others
            warnings.warn(f"pipeline config {path.name} skipped: {exc}", stacklevel=1)


main()
