I changed `dags/fx_pnl_report.py` so the DAG runs at 6am New York time on weekdays and reports the previous business day. The file imports cleanly and I checked the date logic on sample dates. I haven't run the DAG in Airflow.

- **Schedule:** it now uses `CronTriggerTimetable("0 6 * * 1-5", timezone="America/New_York")`, replacing `@daily` at midnight UTC. It stays at 6am New York across daylight saving changes. I also moved `start_date` to New York time.
- **Report date:** the task now works out the previous business day from the run time instead of using `ds`. Monday maps to the prior Friday and Tuesday to Monday. A manual run on a weekend also reports Friday.
- **Dates used:** the run time is converted to New York time before subtracting a day. The date is therefore never taken from UTC.
- **Date checks:** on sample dates, Monday 10/5 gave 10/2, Tuesday 10/6 gave 10/5, and Saturday and Sunday both gave Friday 10/9. Monday 11/2 gave 10/30.
- **Unchanged:** the output file name (`reports/fx_pnl_<date>.csv`), the columns, and the aggregation are the same, so the desk heads' Excel pulls shouldn't break.
- **Holidays:** bank holidays are ignored as you asked. The Tuesday after a Monday holiday will produce an empty report for the holiday, and the desk won't get a report for the last business day before it.

The README says the output is named by trade date, which is still true, so I left it alone.