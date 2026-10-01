# targets: 3.3 2.11
from datetime import date, datetime, timedelta

import pendulum
from airflow.decorators import task


@task
def pick_day():
    day = datetime.now().date()  # expect: wall-clock-in-task
    yesterday = pendulum.now("UTC").subtract(days=1)  # expect: wall-clock-in-task
    window_start = datetime.now() - timedelta(days=7)  # expect: wall-clock-in-task
    label = date.today().strftime("%Y-%m-%d")  # expect: wall-clock-in-task
    return day, yesterday, window_start, label


def build_query():
    cutoff = datetime.utcnow().replace(hour=0, minute=0)  # expect: wall-clock-in-task
    return f"select * from events where ts < '{cutoff}'"
