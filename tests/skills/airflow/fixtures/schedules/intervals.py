"""Schedules whose run/interval semantics differ between Airflow 2.x and 3.x."""

from datetime import datetime, timedelta

from airflow import DAG

try:  # Airflow >= 3.0
    from airflow.sdk import CronDataIntervalTimetable, CronTriggerTimetable
except ImportError:  # Airflow 2.x
    from airflow.timetables.interval import CronDataIntervalTimetable
    from airflow.timetables.trigger import CronTriggerTimetable

try:
    from airflow.providers.standard.operators.empty import EmptyOperator
except ImportError:
    from airflow.operators.empty import EmptyOperator

START = datetime(2026, 1, 1)

with DAG("sched_cron_string", schedule="0 6 * * *", start_date=START, catchup=False):
    EmptyOperator(task_id="noop")

with DAG(
    "sched_cron_interval",
    schedule=CronDataIntervalTimetable("0 6 * * *", timezone="UTC"),
    start_date=START,
    catchup=False,
):
    EmptyOperator(task_id="noop")

with DAG("sched_timedelta", schedule=timedelta(days=1), start_date=START, catchup=False):
    EmptyOperator(task_id="noop")

with DAG(
    "sched_ny_weekdays",
    schedule=CronTriggerTimetable("0 10 * * 1-5", timezone="America/New_York"),
    start_date=START,
    catchup=False,
):
    EmptyOperator(task_id="noop")

with DAG("sched_manual_only", schedule=None, start_date=START, catchup=False):
    EmptyOperator(task_id="noop")

with DAG(
    "sched_catchup_hourly",
    schedule=CronDataIntervalTimetable("0 * * * *", timezone="UTC"),
    start_date=datetime(2025, 1, 1),
    catchup=True,
):
    EmptyOperator(task_id="noop")
