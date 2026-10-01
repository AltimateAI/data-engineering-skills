"""Grader-only DAGs that drive the agent's PartitionPublishedSensor through hidden scenarios."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task

from lake.sensors import PartitionPublishedSensor


@task
def collect(name: str, files, ds=None):
    (Path(os.environ["EVAL_OUT_DIR"]) / f"{name}_{ds}.json").write_text(json.dumps(files))


@dag(schedule=None, start_date=datetime(2026, 9, 1), catchup=False, default_args={"retries": 0})
def eval_lake_wait():
    s = PartitionPublishedSensor(task_id="wait", table="orders", poke_interval=1, timeout=300)
    collect("wait", s.output)


@dag(schedule=None, start_date=datetime(2026, 9, 1), catchup=False,
     default_args={"retries": 2, "retry_delay": timedelta(seconds=3)})
def eval_lake_timeout():
    s = PartitionPublishedSensor(task_id="wait", table="orders", poke_interval=1, timeout=10)
    collect("timeout", s.output)


@dag(schedule=None, start_date=datetime(2026, 9, 1), catchup=False,
     default_args={"retries": 2, "retry_delay": timedelta(seconds=3)})
def eval_lake_softfail():
    s = PartitionPublishedSensor(task_id="wait", table="customers", poke_interval=1, timeout=6, soft_fail=True)
    collect("softfail", s.output)


@dag(schedule=None, start_date=datetime(2026, 9, 1), catchup=False,
     default_args={"retries": 1, "retry_delay": timedelta(seconds=2)})
def eval_lake_outage():
    s = PartitionPublishedSensor(task_id="wait", table="orders", poke_interval=1, timeout=60)
    collect("outage", s.output)


@dag(schedule=None, start_date=datetime(2026, 9, 1), catchup=False, default_args={"retries": 0})
def eval_lake_two_days():
    today = PartitionPublishedSensor(task_id="wait_today", table="orders", partition="{{ ds }}",
                                     poke_interval=1, timeout=300)
    yesterday = PartitionPublishedSensor(task_id="wait_yesterday", table="orders",
                                         partition="{{ macros.ds_add(ds, -1) }}", poke_interval=1, timeout=300)
    today >> yesterday
    collect.override(task_id="collect_today")("today", today.output)
    collect.override(task_id="collect_yesterday")("yesterday", yesterday.output)


@dag(schedule=None, start_date=datetime(2026, 9, 1), catchup=False,
     default_args={"retries": 4, "retry_delay": timedelta(seconds=2)})
def eval_lake_budget():
    @task
    def staging():
        import time

        time.sleep(6)

    s = PartitionPublishedSensor(task_id="wait", table="orders", poke_interval=1, timeout=16)
    staging() >> s
    collect("budget", s.output)


eval_lake_budget()
eval_lake_wait()
eval_lake_timeout()
eval_lake_softfail()
eval_lake_outage()
eval_lake_two_days()
