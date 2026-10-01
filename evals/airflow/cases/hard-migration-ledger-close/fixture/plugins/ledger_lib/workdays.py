"""Business calendar: the workday timetable and the fiscal-period macro."""

from __future__ import annotations

import pendulum
from airflow.timetables.base import DagRunInfo, DataInterval, Timetable

WEEKEND = (pendulum.SATURDAY, pendulum.SUNDAY)


def fiscal_period(day: str) -> str:
    """Fiscal period of a YYYY-MM-DD day; the fiscal year starts on 1 February."""
    d = pendulum.parse(str(day))
    year = d.year + 1 if d.month >= 2 else d.year
    return f"FY{year}-P{(d.month - 2) % 12 + 1:02d}"


def previous_workday(day: pendulum.DateTime) -> pendulum.DateTime:
    day = day.subtract(days=1)
    while day.day_of_week in WEEKEND:
        day = day.subtract(days=1)
    return day


class WorkdayTimetable(Timetable):
    """One run per UTC weekday (Mon-Fri) covering that day, due at the following midnight.

    A manual run covers the latest weekday that has fully ended.
    """

    description = "Every weekday, after the day closes (UTC)"

    @property
    def summary(self) -> str:
        return "workdays"

    def infer_manual_data_interval(self, *, run_after: pendulum.DateTime) -> DataInterval:
        start = previous_workday(pendulum.instance(run_after).in_tz("UTC").start_of("day"))
        return DataInterval(start=start, end=start.add(days=1))

    def next_dagrun_info(self, *, last_automated_data_interval, restriction) -> DagRunInfo | None:
        if last_automated_data_interval is not None:
            start = pendulum.instance(last_automated_data_interval.start).add(days=1)
        else:
            if restriction.earliest is None:
                return None
            start = pendulum.instance(restriction.earliest).in_tz("UTC").start_of("day")
            if not restriction.catchup:
                start = max(start, pendulum.now("UTC").start_of("day").subtract(days=1))
        while start.day_of_week in WEEKEND:
            start = start.add(days=1)
        if restriction.latest is not None and start > restriction.latest:
            return None
        return DagRunInfo.interval(start=start, end=start.add(days=1))
