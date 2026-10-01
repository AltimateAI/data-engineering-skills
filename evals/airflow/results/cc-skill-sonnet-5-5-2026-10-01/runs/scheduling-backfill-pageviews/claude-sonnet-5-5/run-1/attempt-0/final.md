`pageviews_daily` is set up to backfill Sept 1 onward when you unpause it. I tested it on a scratch copy only, not through the real scheduler. The only file changed is `dags/pageviews_daily.py`.

- **Backfill range:** `start_date` is 2026-09-02 UTC and `catchup=True`. The first scheduled run is the 03:00 UTC tick on Sept 2, which loads Sept 1. On unpause, the scheduler creates one run per day through today's 03:00 run, which loads Sept 29. After that it runs daily as before. Nothing earlier than Sept 1 is attempted.
- **One writer at a time:** `max_active_runs=1`, so the backfill days load one after another and never hit the DuckDB lock.
- **Which day a run loads:** it is now taken from the run's own schedule time, one day earlier. The old code used the wall clock ("yesterday"), which would have loaded the wrong day on every backfill, retry or rerun. A manually triggered run has no schedule time, so it uses the trigger time instead, which means it loads the day before the trigger. The schedule also became an explicit `CronTriggerTimetable("0 3 * * *")`, so there is no ambiguity on Airflow 3.
- **Re-running a day:** the delete and insert for that day already happen in one transaction, so a re-run replaces that day instead of adding to it. I left that part unchanged.

I ran `airflow dags test` for the Sept 2 tick, then the Sept 3 tick, then Sept 2 again, all on a copy of the project, and all succeeded. After those runs, Sept 1 had 32 views and Sept 2 had 26, matching the CSV row counts, and the repeat of Sept 2 left them unchanged. Cleaning up the scratch copy left only the DAG edit in git.

I did not run an actual unpause with the scheduler, and I did not run the `airflow_check.py` script from the skill. I never located the skill's bundled scripts and only confirmed that the DAG imports cleanly.

`top_pages_weekly` opens the same DuckDB file read-only. While the backfill is writing (Monday 06:00 is the only time it runs), it could fail with a lock error. Unpausing `pageviews_daily` when that DAG isn't about to fire avoids this, or I can put both DAGs in a one-slot pool.