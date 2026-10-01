`fx_pnl_report` now runs at 6am New York time, Monday to Friday, and each run reports the previous business day. The DAG imports cleanly. I checked the date logic with a small script but did not run the DAG itself.

- **Schedule:** `dags/fx_pnl_report.py` now uses `CronTriggerTimetable("0 6 * * 1-5", timezone="America/New_York")`. It follows daylight saving, so the run is always 6am New York even though the UTC hour shifts.
- **Report date:** Each run takes its trigger time in New York and steps back to the previous weekday. Monday gives Friday and Tuesday gives Monday. A manual run on a Saturday or Sunday also reports Friday.
- **Output:** The report file name (`reports/fx_pnl_<trade date>.csv`) and the columns are unchanged, so the Excel pulls keep working. The file name now carries the reported trade date, which is the previous business day rather than the run date.
- **Other edits:** I switched `start_date` to the New York timezone and updated the docstring and the README row for this DAG.
- **Checked:** The first two rows below are Monday runs. For both Monday-run dates, Friday came out right. The Saturday and Sunday rows are the manual-run case.

| Run date (6am New York) | Reports |
|---|---|
| Mon 2026-10-05 | Fri 2026-10-02 |
| Tue 2026-10-06 | Mon 2026-10-05 |
| Mon 2026-03-09 (DST changeover week) | Fri 2026-03-06 |
| Sat 2026-10-03 / Sun 2026-10-04 | Fri 2026-10-02 |

Bank holidays aren't handled, as you asked. After a holiday the report comes out with no rows.

I haven't committed anything.