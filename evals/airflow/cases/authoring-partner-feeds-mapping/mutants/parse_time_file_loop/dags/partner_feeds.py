"""Process each partner file dropped for the run date as its own mapped task instance."""

from __future__ import annotations

import csv
import json
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import dag, task
from airflow.sdk import TriggerRule

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DROP_DIR = PROJECT_ROOT / "data" / "partner_drop"
OUTPUT_DIR = PROJECT_ROOT / "output" / "partner_feeds"


@dag(
    schedule="0 2 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["partners"],
)
def partner_feeds():
    @task
    def list_partner_files(ds=None) -> list[str]:
        day_dir = DROP_DIR / ds
        return sorted(str(p) for p in day_dir.glob("*.csv")) if day_dir.is_dir() else []

    @task(map_index_template="{{ partner }}")
    def process_file(path: str, ds=None) -> dict:
        from airflow.sdk import get_current_context

        partner = Path(path).stem
        get_current_context()["partner"] = partner
        rows, total = 0, 0.0
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                rows += 1
                total += float(row["amount"])
        result = {"partner": partner, "rows": rows, "total_amount": round(total, 2)}
        out = OUTPUT_DIR / ds / f"{partner}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result))
        return result

    @task(trigger_rule=TriggerRule.NONE_FAILED)
    def write_summary(results, ds=None) -> dict:
        results = list(results or [])
        summary = {
            "files": len(results),
            "rows": sum(r["rows"] for r in results),
            "total_amount": round(sum(r["total_amount"] for r in results), 2),
        }
        out = OUTPUT_DIR / ds / "summary.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary))
        return summary

    results = []
    for day_dir in sorted(DROP_DIR.glob("*")):
        for f in sorted(day_dir.glob("*.csv")):
            results.append(process_file.override(task_id=f"process_{day_dir.name}_{f.stem}".replace("-", "_"))(str(f)))
    list_partner_files() >> write_summary(results)


partner_feeds()
