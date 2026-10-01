"""Builds one DAG per pipeline config in configs/pipelines/*.yaml.

Each config names its team (looked up in the platform registry for owners and
retry defaults), a schedule (hour and day-of-week; the start minute is spread
over the hour so the warehouse does not get every pipeline at :00) and a list
of steps. Every step becomes a task that runs `run_step`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs" / "pipelines"
REGISTRY = PROJECT_ROOT / "configs" / "registry.yaml"
OUTPUT_DIR = PROJECT_ROOT / "output"


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
        return yaml.load(fh, Loader=yaml.SafeLoader)


def check_table(registry: dict, table: str) -> None:
    if table not in registry["datasets"]:
        raise ValueError(f"unknown table {table!r}: register it in the platform catalog first")


def start_minute(name: str) -> int:
    # Spread pipelines over the hour so they do not all hit the warehouse at :00.
    return hash(name) % 60


def build_dag(path: Path) -> DAG:
    cfg = load_yaml(path)
    registry = load_yaml(REGISTRY)
    team = registry["teams"][cfg["team"]]
    sched = cfg["schedule"]
    minute = sched.get("minute", start_minute(cfg["name"]))
    owners = set(team["owners"]) | set(cfg.get("owners", []))

    dag = DAG(
        dag_id=cfg["name"],
        description=cfg.get("description"),
        schedule=f"{minute} {sched['hour']} * * {sched.get('days', '*')}",
        start_date=datetime(2026, 1, 1),
        catchup=False,
        tags=[cfg["team"], "fleet"],
        doc_md=f"Generated from `{path.name}` on {datetime.now():%Y-%m-%d %H:%M}. "
               f"On-call: {team['oncall']} ({team['slack']}).",
        default_args={
            "owner": ",".join(owners),
            "retries": cfg.get("retries", team["default_retries"]),
            "retry_delay": timedelta(minutes=5),
        },
    )
    with dag:
        tasks = {}
        for step in cfg["steps"]:
            check_table(registry, step["table"])
            tasks[step["name"]] = PythonOperator(
                task_id=step["name"],
                python_callable=run_step,
                op_kwargs={"pipeline": cfg["name"], "step": step["name"], "table": step["table"]},
            )
        for step in cfg["steps"]:
            for upstream in step.get("depends_on", []):
                tasks[upstream] >> tasks[step["name"]]
    return dag


for config_path in CONFIG_DIR.glob("*.yaml"):
    dag = build_dag(config_path)
    globals()[dag.dag_id] = dag
