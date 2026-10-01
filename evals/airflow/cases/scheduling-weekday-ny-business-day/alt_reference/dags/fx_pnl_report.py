"""Daily FX P&L report for the trading desks.

Weekday 06:00 New York schedule with data intervals: each run's interval spans
from the previous weekday 06:00 to this one, so the interval start is the
business day being reported (Monday's interval starts on Friday).
"""

import csv
from collections import defaultdict
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, CronDataIntervalTimetable

PROJECT_DIR = Path(__file__).resolve().parents[1]
TRADES_CSV = PROJECT_DIR / "data" / "fx_trades.csv"
REPORTS_DIR = PROJECT_DIR / "reports"


def write_pnl_report(trade_date: str) -> str:
    totals: dict[str, list[float]] = defaultdict(lambda: [0, 0.0, 0.0])
    with TRADES_CSV.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["trade_date"] == trade_date:
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
    return str(out)


with DAG(
    dag_id="fx_pnl_report",
    schedule=CronDataIntervalTimetable("0 6 * * MON-FRI", timezone="America/New_York"),
    start_date=pendulum.datetime(2026, 1, 1, 6, tz="America/New_York"),
    catchup=False,
    default_args={"owner": "treasury-data"},
    tags=["treasury", "reports"],
):
    PythonOperator(
        task_id="build_report",
        python_callable=write_pnl_report,
        op_kwargs={
            "trade_date": "{{ data_interval_start.in_timezone('America/New_York').strftime('%Y-%m-%d') }}",
        },
    )
