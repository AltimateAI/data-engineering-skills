`fx_pnl_report` now runs at 6am New York time, Monday to Friday, and each run reports the previous business day. The change is only in `dags/fx_pnl_report.py`.

- **Schedule:** the cron is `0 6 * * 1-5` with the `America/New_York` timezone, so it stays at 6am local across daylight saving changes. `start_date` is now also New York time.
- **Date:** the DAG works out the previous business day from the run time, in New York time. Monday's run reports Friday and Tuesday's reports Monday. A manual trigger follows the same rule, based on when you trigger it. Rerunning a day produces the same report as the original run.
- **File name and columns:** unchanged. It still writes `reports/fx_pnl_<trade date>.csv` with `desk,trades,notional_usd,pnl_usd`.
- **Holidays:** a run on a bank holiday reports the day before, even if that was also a holiday.

**Verified** (Airflow 3.3.2):
- **Import check:** it passes with no errors. The next scheduled runs are Oct 1, 2, 5, 6, 7 and 8 at 10:00 UTC, which is 6am New York in the current daylight-saving period. It warns that the schedule fires on the run day itself. That is expected, because the DAG computes the earlier day itself.
- **Monday run:** a test run for Monday 2026-03-02 at 6am wrote `fx_pnl_2026-02-27.csv`, Friday's report.
- **Tuesday run:** a test run for Tuesday 2026-03-10 wrote `fx_pnl_2026-03-09.csv`.
- **Manual trigger:** a manual trigger with no date on Tuesday 2026-03-03 wrote the 2026-03-02 report.

**Not verified:**
- I did not run several consecutive scheduled runs back to back, though the DAG keeps no state between runs.
- I did not run the DAG on a live scheduler.
- I did not run a test across a daylight-saving change.
- I did not compare the output against the existing reports the desk heads pull into Excel.

The test runs wrote files into `reports/` and `airflow.cfg`. I deleted both, so only the DAG edit is left in the working tree. I haven't committed anything.