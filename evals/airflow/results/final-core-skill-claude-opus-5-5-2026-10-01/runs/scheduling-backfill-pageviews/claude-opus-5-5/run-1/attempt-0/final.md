`pageviews_daily` is ready: when you unpause it, it loads Sept 1 first, works through every day since then one at a time, and then runs daily. I tested it with local runs against a throwaway Airflow database, not with the real scheduler; the results are below. The only file changed is `dags/pageviews_daily.py`.

**How it schedules:**
- It runs at 03:00 UTC and loads the previous UTC day's file, so the run on Oct 2 loads Oct 1. That leaves two hours after the web tier drops the file at about 01:00.
- The first run is Sept 2 at 03:00, which loads Sept 1. The schedule preview confirms nothing earlier gets scheduled.
- Catch-up is on, so unpausing creates about 30 runs that fill Sept 1 onward, and then it carries on daily.

**One writer at a time:** only one run of the DAG can be active at once. The catch-up runs go through one day after another instead of up to 16 starting together.

**Re-runs don't double count:** each run deletes that day's rows and inserts them fresh, in one transaction. To redo a day you can:
- **Clear an existing run:** it reloads the same day as the original. The day now comes from the run's own date instead of the clock; the old code used "now minus one day", so a backfill or clear would have loaded the wrong day.
- **Trigger it with `{"day": "2026-09-15"}`:** this reloads that specific day.

A manual trigger with no date loads the day before the trigger.

**Missing file:** if a day's file is missing, the run fails with a clear "raw export not found" error instead of silently loading nothing. It retries once after 5 minutes.

**What I tested:**
- The DAG parses cleanly.
- Three scheduled runs loaded Sept 1, 2 and 3, and the view totals match the raw row counts (32, 26 and 22).
- I re-ran Sept 1 and Sept 2 and triggered Sept 15 twice: every day had exactly one row per page, with no duplicates.
- A manual run on Sept 10 loaded Sept 9.
- A run for Sept 30 failed as expected, because there's no file for it.

I deleted the test `warehouse/` afterwards.

**Two things to know:**
1. **The Sept 30 file is missing.** `data/pageviews/` only goes up to 2026-09-29, so the Sept 30 run (03:00 Oct 1) will fail when you unpause. The other days still load. Once the file arrives, clear that run.
2. **The weekly DAG can collide with this one.** `top_pages_weekly` opens the same DuckDB file read-only. DuckDB won't let another process open the file while a writer holds it, so if its Monday 06:00 run lands while a daily load is writing, it will hit a lock error. Each daily load takes only a few seconds, so this is unlikely, but it's possible during the first catch-up. If you want that ruled out, I can put both tasks on a shared one-slot Airflow pool.