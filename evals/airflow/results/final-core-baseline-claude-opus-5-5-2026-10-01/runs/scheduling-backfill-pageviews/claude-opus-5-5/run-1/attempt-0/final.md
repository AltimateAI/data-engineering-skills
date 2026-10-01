`pageviews_daily` is ready to unpause. When you do, it will load every day from Sept 1 onward, one day at a time, and then keep going daily. The change is all in `dags/pageviews_daily.py`.

**The main bug:** the old task picked its day from the current clock (`pendulum.now() - 1 day`), not from the run's own date. So with catchup on, every catch-up run would have reloaded yesterday's file instead of its own day. Each run now works out its day from its own scheduled date, so catch-up runs, backfills and re-runs each load the right file.

**Schedule**
- It runs daily at 03:00 UTC (about two hours after the 01:00 file drop) and loads the previous UTC day.
- The first run is at Sept 2 03:00, which loads Sept 1. I confirmed this against the scheduler's timetable, so nothing before Sept 1 is ever requested.
- Catchup is now on, so unpausing creates all the runs since then.

**One day at a time:** only one run of this DAG can be active at once, and only one task within it, so this DAG never opens two writers on `web.duckdb`.

**Re-runs:** the existing load already deleted the day's rows and reinserted them in one transaction, so I kept that. I ran Sept 1 twice and then Sept 2 in a throwaway Airflow setup. Sept 1 held steady at 8 pages and 32 views after both runs, matching the raw CSV, and Sept 2 sat alongside it. To redo a day later, just clear that run in the UI.

**Missing files:** if a day's file isn't there, the task now fails with a clear "Raw export for … not found" error. It retries 3 times, 30 minutes apart, then fails. That's better than quietly writing zero rows. A failed day doesn't hold up later days, and you can clear it once the file arrives.

Two things to know before unpausing:
1. **`data/pageviews/2026-09-30.csv` isn't there yet.** The files stop at Sept 29, so today's run for Sept 30 will fail until the file shows up. In my test it failed exactly like that.
2. **`top_pages_weekly` can still hit the database lock.** It opens `web.duckdb` read-only on Mondays at 06:00, and DuckDB won't allow that while another process is writing. The catch-up only writes for a few seconds per day, so a clash is unlikely, but it's possible if you unpause just before a Monday 06:00 run. The fix is an Airflow pool with one slot that both DAGs use, but someone has to create that pool first. Alternatively, avoid unpausing right before a Monday 06:00 run. I didn't add the pool, but can if you want.

I deleted all the test files afterwards, including the local warehouse file. Nothing is committed yet.