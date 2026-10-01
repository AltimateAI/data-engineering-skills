I fixed `dags/partner_feed.py`, which is the only file I changed. In a local replay, the scheduled runs and a manual trigger without a date both finish and produce the right day's files. Nothing is committed yet.

## What was wrong

There were three problems. Only the first two showed up as errors.

1. **`write_manifest`: `KeyError: 'execution_date'`.** Airflow 3 no longer has `execution_date`.
2. **Manual trigger: `KeyError: 'logical_date'`.** A manual run in Airflow 3 with the date left empty has no logical date, so `logical_date` and `ds` don't exist. `extract_orders` failed first; `deliver`'s `{{ ds_nodash }}` would have failed the same way.
3. **The nightly run had also switched days without any error.** In Airflow 3, a plain cron string like `"0 4 * * *"` gives the run the date it fires on. So the 04:00 run on 03-03 started extracting 03-03, an incomplete day, instead of 03-02 as before the upgrade. You didn't see this because `write_manifest` crashed before anything reached the outbox.

## The fix

- **Schedule:** `CronDataIntervalTimetable("0 4 * * *", timezone="UTC")`. Same 04:00 UTC run time, and each run's date is the previous day again, as before. `catchup=False` is unchanged.
- **Which day to produce:** one helper, `feed_day(dag_run)`, used by `extract_orders` and `write_manifest`. `deliver` uses the same rule in its template. It returns the run's date if it has one; otherwise the UTC day the run was triggered (`dag_run.run_after`).
  - That trigger time is saved with the run, so clearing and re-running it tomorrow should still produce the trigger day. I didn't actually clear and re-run a run to confirm this.
  - It never reads the current clock.
- **Unchanged:** the task ids, the extract → manifest → deliver order, `output/partner_feed/<YYYY-MM-DD>/{orders.csv,manifest.json}`, and `outbox/acme/acme_orders_<YYYYMMDD>.{csv,manifest.json}`.

## Verification

- **Static checks:** the Airflow 3 checker reports no problems and ruff's Airflow rules pass. The 04:00 fire times and run dates match what the old setup would have produced.
- **Replay:** three nightly runs (firing 03-03 to 03-05) succeeded. They produced the 03-02, 03-03 and 03-04 feeds with 4, 6 and 6 rows, which matches ACME's orders in `data/partner_orders.csv`.
- **Manual triggers without a date:** a trigger at 2026-03-03 23:30Z produced the 03-03 feed. One at 2026-03-01 23:59Z produced `acme_orders_20260301.*`.
- **Not compared against the old version:** there's no Airflow 2 install here, so I couldn't run the pre-upgrade code and diff its files against the new ones. The run dates were checked using Airflow 2's date rules, and I checked file contents against the source CSV by hand.
- **Cleanup:** one of my test runs wrote files into your `output/` and `outbox/` folders. I deleted them, so the only change in the repo is the DAG file.

## Things to watch

- **Missed feeds from the past week:** ACME has had nothing delivered since the upgrade. Clearing those failed runs won't give the right days, because they were created under the old schedule and are stored with the day they fired on. Re-running one would produce the feed for its fire date, not the day before. To fill in the missed feeds, trigger the DAG manually once per missing day with that date as the logical date; with the new schedule, the logical date is the feed day.
- **Stray files:** `output/partner_feed/` on the server may have incomplete same-day `orders.csv` files from that week. The proper re-runs will overwrite them.
- **Same-day feeds:** a manual trigger without a date produces a feed for a day that isn't over yet, so it's partial, as you specified. If the 04:00 run on the next day isn't paused, it rewrites that day's feed in full.
- **`partner_catalog_sync`** uses the same kind of bare cron string. It never reads a date and still runs at Monday 06:00, so it's unaffected and I left it alone.