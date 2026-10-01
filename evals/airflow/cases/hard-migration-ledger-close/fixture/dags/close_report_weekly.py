"""Weekly close report: net movement per account over the closed business days of
the week, compared with the previous weekly report.

Output: output/reports/week_<week start>.csv
"""

from __future__ import annotations

import csv
from collections import defaultdict

import pendulum
from airflow.decorators import dag, task

from ledger_lib import OUTPUT_DIR

CLOSE_DIR = OUTPUT_DIR / "close"
REPORT_DIR = OUTPUT_DIR / "reports"


@dag(
    schedule_interval="0 7 * * 1",
    start_date=pendulum.datetime(2026, 2, 23, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "finance-data"},
    tags=["ledger", "reporting"],
)
def close_report_weekly():
    @task
    def weekly_report(ds=None, prev_ds=None, data_interval_start=None) -> str:
        week_start = pendulum.instance(data_interval_start).start_of("day")
        totals: dict[str, int] = defaultdict(int)
        closed = []
        for offset in range(5):
            day = week_start.add(days=offset).strftime("%Y-%m-%d")
            net = CLOSE_DIR / day / "net.csv"
            if not net.exists():
                continue
            closed.append(day)
            with net.open(newline="") as fh:
                for row in csv.DictReader(fh):
                    totals[row["account"]] += int(row["net_cents"])

        previous: dict[str, int] = {}
        prev_report = REPORT_DIR / f"week_{prev_ds}.csv"
        if prev_report.exists():
            with prev_report.open(newline="") as fh:
                previous = {r["account"]: int(r["net_cents"]) for r in csv.DictReader(
                    line for line in fh if not line.startswith("#"))}

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        with (REPORT_DIR / f"week_{ds}.csv").open("w", newline="") as fh:
            fh.write(f"# week of {ds}; closed days: {', '.join(closed) or 'none'}; "
                     f"compared with the report for the week of {prev_ds}\n")
            writer = csv.writer(fh)
            writer.writerow(["account", "net_cents", "previous_week_net_cents", "change_cents"])
            for account in sorted(set(totals) | set(previous)):
                now, before = totals.get(account, 0), previous.get(account, 0)
                writer.writerow([account, now, before, now - before])
        return ds

    weekly_report()


close_report_weekly()
