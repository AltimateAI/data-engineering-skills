`fx_pnl_report` now runs at 06:00 New York time on weekdays and reports the previous business day. The change is only in `dags/fx_pnl_report.py`, and I haven't committed it.

- **Schedule:** it uses a New York cron for 06:00 Monday to Friday. Because the cron is in New York time, it stays at 06:00 local across daylight-saving changes.
- **Report date:** Monday reports Friday and Tuesday reports Monday. Bank holidays aren't handled, as you said.
- **Output:** the file name and columns are unchanged, and the file is named for the day reported (`fx_pnl_<trade date>.csv`).
- **Reruns and manual runs:** a manual run on Airflow 3 has no logical date, so it uses the time it was triggered, with the same previous-business-day rule. A rerun reports the same day as the original run. I also added an optional `day` parameter (YYYY-MM-DD) to rebuild a specific trade date.
- **Catch-up:** `catchup=False` is set explicitly, so deploying won't backfill history.

I checked it on Airflow 3.3.2:
- **Static check:** it passes with no errors. Its one warning says the run time isn't the reported day, which is intended here.
- **Next runs:** 2026-09-30, 10-01, 10-02 and 10-05, each at 06:00 New York, skipping the weekend.
- **Test runs:**
  - The Monday 2026-03-09 run wrote `fx_pnl_2026-03-06.csv`, the Friday.
  - The Tuesday 2026-03-10 run wrote `fx_pnl_2026-03-09.csv`.
  - A manual trigger on 2026-03-10 also wrote `fx_pnl_2026-03-09.csv`, overwriting the same file.
- **Contents:** the 2026-03-06 file has the same columns as before, with per-desk totals.

I deleted the test report files afterwards and did not run a real scheduler.

The trade export (`data/fx_trades.csv`) already has Monday-to-Friday trade dates through 2026-11-06. If a trade ever lands on a weekend date, no run will report it.