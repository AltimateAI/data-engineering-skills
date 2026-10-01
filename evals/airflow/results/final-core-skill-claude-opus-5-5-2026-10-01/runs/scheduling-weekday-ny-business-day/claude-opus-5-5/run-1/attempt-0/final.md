`fx_pnl_report` now runs every weekday at 06:00 New York time and reports the previous business day. Monday's run reports Friday, Tuesday's reports Monday, and so on. The only file changed is `dags/fx_pnl_report.py`; it isn't committed.

**What changed**
- **Schedule:** it now uses a cron schedule set in New York time (`0 6 * * 1-5`, `America/New_York`) instead of `@daily` UTC. It stays at 6am local when the clocks change: 11:00 UTC in winter, 10:00 UTC in summer.
- **Report date:** a new helper, `report_trade_date`, works out the New York date the run fired on and steps back to the previous weekday. This replaces the old `ds`, which was the run's own UTC date.
- **Manual runs:** a manual trigger with no date follows the same rule, based on when it was triggered. Before this change, a manual run had no date to work from and would have failed.
- **Reprocessing a day:** you can trigger with `{"day": "YYYY-MM-DD"}` to re-run a specific trade date.
- **One run at a time:** I set `max_active_runs=1`. It isn't strictly needed, because each run writes only its own file.
- **Unchanged:** the file name `reports/fx_pnl_<trade date>.csv`, the columns `desk, trades, notional_usd, pnl_usd`, and the aggregation code.

**Checks run** (Airflow 3.3.2, matching `requirements.txt`)
- **Schedule preview:** the next 8 runs land on Monday–Friday only, at 06:00 New York, including across the March DST change.
- **`airflow dags test` for Mon 2026-03-09:** it wrote `fx_pnl_2026-03-06.csv` (the Friday), with the same header as before, and all 7 of that day's trades were counted.
- **Four consecutive scheduled runs across the November DST change:**

  | Run | Report written |
  |---|---|
  | Thu 10-29 | `fx_pnl_2026-10-28.csv` |
  | Fri 10-30 | `fx_pnl_2026-10-29.csv` |
  | Mon 11-02 | `fx_pnl_2026-10-30.csv` |
  | Tue 11-03 | `fx_pnl_2026-11-02.csv` |

- **Manual trigger Monday 11-02 at 10:30 New York:** it wrote Friday's report.
- **Override `day=2026-02-27`:** it wrote that day's report.
- **Re-running the same day:** it overwrote the file with identical content, with no duplicate rows.

I deleted the test reports and the temporary Airflow files afterwards.

**Not handled or not checked**
- **Holidays:** as agreed, they aren't skipped. A run the morning after a holiday will report the holiday itself, which will probably be an empty file. Adding a holiday calendar later only means changing `prev_business_day`.
- **Real scheduler:** I didn't run it under a live scheduler, only `dags test` and simulated runs.
- **After deploy:** with `catchup=False`, the DAG will run once straight away for the most recent weekday 6am slot it missed. Weekend runs stop.