I changed `report_day` in `scripts/nightly_report.py` to take the local calendar date and subtract one day. I haven't run it or added a test.

The old code subtracted 24 hours from the current time. On a DST change day, a local day is 23 or 25 hours long. If the job ran shortly after midnight, 24 hours back could land on the wrong date. A job that ran at 00:30 on the day clocks go back would report two days ago instead of yesterday.

The new line is `now.date() - dt.timedelta(days=1)`. Date arithmetic doesn't depend on how many hours the day had, so it always gives yesterday in local time. `now` is still the naive local `datetime.now()`, so the "local time" meaning is unchanged.