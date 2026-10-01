I've changed `fx_pnl_report` (only `dags/fx_pnl_report.py`). It now runs at 6:00am New York time, Monday to Friday, and each run reports the previous business day. The file name and columns are unchanged.

**What changed**
- **Schedule:** it now uses a cron schedule (`0 6 * * 1-5`) set to New York time instead of `@daily` in UTC. It moves with daylight saving automatically, so it runs at 11:00 UTC in winter and 10:00 UTC in summer.
- **Report date:** a new helper, `previous_business_day`, converts the run time to New York time, steps back one day, and keeps stepping back past Saturday and Sunday. That date goes into the existing `write_pnl_report`. Bank holidays are not skipped, as you asked.
- **Manual triggers:** a manually triggered run with no scheduled date falls back to its actual run time. Triggered on a weekend, it reports Friday.

**Checks I ran**
- Airflow 3.3.2 loads the DAG with no import errors.
- I printed the actual scheduled runs from 5 to 16 March 2026, across the daylight saving change:
  - Runs only fall Monday to Friday, always at 06:00 New York time.
  - Monday 9 March reports Friday 6 March. Tuesday reports Monday, and so on.
- Saturday and Sunday run times both give Friday. 00:30 New York on 10 March gives 9 March, which shows the date is taken in New York time, not UTC.
- A sample report for 2026-02-23 came out as `reports/fx_pnl_2026-02-23.csv` with the same header (`desk,trades,notional_usd,pnl_usd`). I deleted that test file afterwards.

**Things to know**
- The report date is no longer the same as the run's own date. If someone reruns or backfills, say, Tuesday's run, it produces Monday's report.
- The old schedule may have been reporting the wrong day. Midnight UTC is 8pm New York the evening before, so it may have been reporting a trading day that hadn't happened yet. That depends on an Airflow setting I can't see from here. If the desk has had empty or partial files, that's probably why, and the new schedule fixes it.
- On the first morning under the new schedule, the previous business day may get a second file or overwrite one the old schedule already wrote. Same name and columns, so it should be harmless.

Nothing is committed yet. Tell me if you want a commit or PR.