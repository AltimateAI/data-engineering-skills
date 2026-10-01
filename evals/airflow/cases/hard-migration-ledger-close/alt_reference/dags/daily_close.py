"""Daily close of each business day: net movements per account, then rolled balances.

``net_movements`` aggregates the postings booked during the business day
(sql/daily_close.sql); ``roll_balances`` adds them to the previous business
day's closing balances. Output: output/close/<day>/{net.csv,net.meta.json,balances.csv}.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pendulum
from airflow.sdk import dag, task

from ledger_lib import DATA_DIR, OUTPUT_DIR
from ledger_lib.workdays import WorkdayTimetable, previous_workday
from ledger_lib.operators import DuckDbSqlOperator

CLOSE_DIR = OUTPUT_DIR / "close"


def close_window(dag_run) -> tuple[pendulum.DateTime, pendulum.DateTime]:
    """Business day closed by a run. A CLI trigger has no data interval on Airflow 3, so it
    gets the timetable's manual interval (the latest business day that has ended)."""
    if dag_run.data_interval_start is not None:
        return pendulum.instance(dag_run.data_interval_start), pendulum.instance(dag_run.data_interval_end)
    start = previous_workday(pendulum.instance(dag_run.run_after).in_tz("UTC").start_of("day"))
    return start, start.add(days=1)


def read_accounts(path: Path, column: str) -> dict[str, int]:
    if not path.exists():
        return {}
    with path.open(newline="") as fh:
        return {row["account"]: int(row[column]) for row in csv.DictReader(fh)}


@dag(
    schedule=WorkdayTimetable(),
    start_date=pendulum.datetime(2026, 3, 2, tz="UTC"),
    catchup=True,
    max_active_runs=1,
    template_searchpath=[str(Path(__file__).parent / "sql")],
    params={"postings": str(DATA_DIR / "postings.csv")},
    user_defined_macros={"close_window": close_window},
    default_args={"owner": "finance-data", "retries": 1},
    tags=["ledger", "close"],
)
def daily_close():
    net = DuckDbSqlOperator(
        task_id="net_movements",
        sql="daily_close.sql",
        target="output/close/{{ close_window(dag_run)[0] | ds }}/net.csv",
    )

    @task
    def roll_balances(dag_run=None) -> int:
        day = close_window(dag_run)[0]
        opening = read_accounts(CLOSE_DIR / previous_workday(day).strftime("%Y-%m-%d") / "balances.csv",
                                "closing_cents")
        movements = read_accounts(CLOSE_DIR / day.strftime("%Y-%m-%d") / "net.csv", "net_cents")
        with (CLOSE_DIR / day.strftime("%Y-%m-%d") / "balances.csv").open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["account", "opening_cents", "net_cents", "closing_cents"])
            for account in sorted(set(opening) | set(movements)):
                o, n = opening.get(account, 0), movements.get(account, 0)
                writer.writerow([account, o, n, o + n])
        return len(set(opening) | set(movements))

    net >> roll_balances()


daily_close()
