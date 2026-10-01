I fixed `report_day` in `scripts/nightly_report.py`. I haven't run it or added a test.

It used to subtract 24 hours from the current time and then take the date. On a daylight saving day that isn't 24 hours long, the result could land on the wrong date. A run shortly after midnight could report the day before yesterday, or yesterday could be skipped.

It now takes today's local date and subtracts one calendar day: `now.date() - dt.timedelta(days=1)`. That always gives yesterday's local date, whatever the length of the days involved.