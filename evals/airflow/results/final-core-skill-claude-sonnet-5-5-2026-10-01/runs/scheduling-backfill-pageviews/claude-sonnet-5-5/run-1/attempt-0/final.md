`pageviews_daily` is set up so that unpausing it loads every day from Sept 1 and then continues daily. I ran the first three scheduled days, a manual run and a rerun, and all succeeded. I did not run the full backfill.

**What changed (`dags/pageviews_daily.py`)**
- **Start and catchup:** `start_date` is now 2026-09-02 and `catchup=True`. The run that fires at 03:00 UTC on day D loads day D-1, as before. The first run is the Sept 2 03:00 tick, which loads Sept 1, so nothing earlier is attempted.
- **One day at a time:** `max_active_runs=1` and `max_active_tasks=1` mean the backfill writes one day at a time, so there is no DuckDB lock contention within this DAG.
- **Day loaded:** it comes from the run's own date, not `now()`. Before, a backfill would have loaded yesterday's file for every run. Manual runs, which have no logical date on Airflow 3, load the day before the trigger.
- **Rerunning a day:** you can pass `{"day": "2026-09-05"}` as params to reload a specific day.
- **No double counting:** a day's rows are deleted and reinserted in one transaction, which now rolls back on error. Rerunning Sept 2 left exactly one set of rows per page, and the Sept 1 total of 32 views matched the CSV.
- **Missing file:** the task now fails clearly with `FileNotFoundError` when a day's CSV doesn't exist.

**What I ran**
- `airflow_check.py` exits 0. The schedule previews Sept 2, 3, 4 at 03:00 UTC.
- `replay_runs.py` ran three consecutive days, a manual trigger at Sept 10 09:30, and a rerun of Sept 2. All five succeeded. The manual trigger loaded Sept 9, as intended.
- I deleted the throwaway `warehouse/` and `tmp/` directories I created, so the repo shows only the DAG change.

**Things to know before unpausing**
- **Sept 30 will fail.** Your files end at 2026-09-29. The last backfill run, the one that loads Sept 30, will fail until that export lands. Its retry will fail too, and the day will load once you clear it after the file arrives.
- **`top_pages_weekly` can hit a lock.** It opens the same DuckDB file, and its Monday 06:00 run could collide with a backfill load. I left it alone. If that matters, put both DAGs' DuckDB tasks in a one-slot pool.
- **Not tested.** I didn't run the real scheduler through all 29 backfill runs.