"""Partner feeds mapped over the partner registry (only registered partners are picked up)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pendulum
from airflow.sdk import TriggerRule, dag, task

ROOT = Path(__file__).resolve().parents[1]
DROP = ROOT / "data" / "partner_drop"
OUT = ROOT / "output" / "partner_feeds"


@dag(schedule="0 2 * * *", start_date=pendulum.datetime(2026, 9, 1, tz="UTC"), catchup=False)
def partner_feeds():
    @task
    def files_for_day(ds=None) -> list[str]:
        registry = json.loads((ROOT / "data" / "partners.json").read_text())
        return [str(DROP / ds / f"{p}.csv") for p in sorted(registry) if (DROP / ds / f"{p}.csv").exists()]

    @task
    def process(path: str, ds=None) -> dict:
        with open(path, newline="") as fh:
            amounts = [float(r["amount"]) for r in csv.DictReader(fh)]
        res = {"partner": Path(path).stem, "rows": len(amounts), "total_amount": round(sum(amounts), 2)}
        (OUT / ds).mkdir(parents=True, exist_ok=True)
        (OUT / ds / f"{res['partner']}.json").write_text(json.dumps(res))
        return res

    @task(trigger_rule=TriggerRule.NONE_FAILED)
    def summary(results, ds=None) -> None:
        results = list(results or [])
        (OUT / ds).mkdir(parents=True, exist_ok=True)
        (OUT / ds / "summary.json").write_text(json.dumps({
            "files": len(results), "rows": sum(r["rows"] for r in results),
            "total_amount": round(sum(r["total_amount"] for r in results), 2)}))

    summary(process.expand(path=files_for_day()))


partner_feeds()
