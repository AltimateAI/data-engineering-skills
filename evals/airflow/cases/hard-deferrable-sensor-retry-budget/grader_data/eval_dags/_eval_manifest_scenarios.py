"""Grader-only DAGs that drive the agent's PartnerManifestSensor through hidden scenarios."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task

from partners.sensors import PartnerManifestSensor


@task
def collect(name: str, files, ds=None):
    (Path(os.environ["EVAL_OUT_DIR"]) / f"{name}.json").write_text(json.dumps(files))


@task
def staging(seconds: float):
    time.sleep(seconds)


def _dag(dag_id, *, timeout, retries=0, soft_fail=False, staging_s=0.0):
    @dag(dag_id=dag_id, schedule=None, start_date=datetime(2026, 9, 1), catchup=False,
         default_args={"retries": retries, "retry_delay": timedelta(seconds=2)})
    def _d():
        s = PartnerManifestSensor(task_id="wait", partner="acme", poke_interval=1, timeout=timeout,
                                  soft_fail=soft_fail)
        staging(staging_s) >> s
        collect(dag_id, s.output)

    return _d()


_dag("eval_manifest_ok", timeout=60)
_dag("eval_manifest_budget", timeout=16, retries=4, staging_s=6.0)
_dag("eval_manifest_restart", timeout=12, retries=2)
_dag("eval_manifest_softfail_outage", timeout=60, retries=3, soft_fail=True)
_dag("eval_manifest_softfail_timeout", timeout=6, retries=2, soft_fail=True)
