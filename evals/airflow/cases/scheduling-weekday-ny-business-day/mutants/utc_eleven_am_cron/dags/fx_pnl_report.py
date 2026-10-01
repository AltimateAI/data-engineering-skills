"""Daily FX P&L report for the trading desks.

Runs at 06:00 America/New_York on weekdays and reports the previous business
day (Monday's run reports Friday). Reads the booked trades export
(data/fx_trades.csv, one row per trade with the New York trade date) and writes
reports/fx_pnl_<trade date>.csv with per-desk totals.
"""

import csv
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pendulum
from airflow.sdk import CronTriggerTimetable, dag, task

PROJECT_DIR = Path(__file__).resolve().parents[1]
TRADES_CSV = PROJECT_DIR / "data" / "fx_trades.csv"
REPORTS_DIR = PROJECT_DIR / "reports"
NEW_YORK = "America/New_York"


def previous_business_day(day: date) -> date:
    """The weekday before ``day`` (holidays are not considered)."""
    prev = day - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev


def write_pnl_report(trade_date: str) -> Path:
    """Aggregate the trades booked on ``trade_date`` (YYYY-MM-DD) per desk."""
    totals: dict[str, list[float]] = defaultdict(lambda: [0, 0.0, 0.0])
    with TRADES_CSV.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["trade_date"] != trade_date:
                continue
            t = totals[row["desk"]]
            t[0] += 1
            t[1] += float(row["notional_usd"])
            t[2] += float(row["pnl_usd"])
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"fx_pnl_{trade_date}.csv"
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["desk", "trades", "notional_usd", "pnl_usd"])
        for desk in sorted(totals):
            count, notional, pnl = totals[desk]
            writer.writerow([desk, count, f"{notional:.2f}", f"{pnl:.2f}"])
    return out


@dag(
    dag_id="fx_pnl_report",
    # 06:00 in New York is 11:00 UTC
    schedule=CronTriggerTimetable("0 11 * * 1-5", timezone="UTC"),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "treasury-data"},
    tags=["treasury", "reports"],
)
def fx_pnl_report():
    @task
    def build_report(logical_date=None) -> str:
        run_day = pendulum.instance(logical_date).in_timezone(NEW_YORK).date()
        return str(write_pnl_report(previous_business_day(run_day).isoformat()))

    build_report()


fx_pnl_report()
