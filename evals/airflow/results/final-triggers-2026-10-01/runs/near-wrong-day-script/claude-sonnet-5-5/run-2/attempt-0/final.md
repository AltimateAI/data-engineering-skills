I fixed `report_day` in `scripts/nightly_report.py`. I haven't run it or added a test.

The old code subtracted 24 hours from the current time and took the date. On a DST day that can land on the wrong date. A run shortly after midnight on a 25-hour day (clocks go back) would still report the day before yesterday. The same thing can happen the other way on a 23-hour day.

It now takes today's local date and subtracts one calendar day, so it doesn't depend on how long the day was. A normal run returns the previous local date, and DST changes no longer matter.