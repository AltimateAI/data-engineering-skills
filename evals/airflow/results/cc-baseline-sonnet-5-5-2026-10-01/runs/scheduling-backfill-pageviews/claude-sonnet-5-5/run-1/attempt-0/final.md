`pageviews_daily` is set up so that when you unpause it, the scheduler loads Sept 1 through Sept 29 one day at a time. After that it runs daily. I checked that the DAG file imports and that the settings below are in effect. I haven't run it against the warehouse or run the backfill itself.

The change is in `dags/pageviews_daily.py`:

- **Backfill:** `start_date` is now 2026-09-01 and `catchup` is `True`, so nothing before Sept 1 is scheduled. The run at 03:00 on day N+1 loads day N, and the 09-02 03:00 run loads Sept 1.
- **Which day each run loads:** The task used to load "yesterday" from the clock, so every backfill run would have loaded the same day. It now loads the day its run covers (`data_interval_start`). A bare cron string in Airflow 3 would also have shifted every run one day, so I used an explicit `CronDataIntervalTimetable("0 3 * * *")`.
- **One writer at a time:** `max_active_runs=1` means the scheduler runs only one day at a time, and that includes any backfills or re-runs you start.
- **Re-runs without double counting:** The load already deleted the day's rows and inserted fresh ones in one transaction, so re-running a day replaces its rows. I added an explicit rollback on failure, so a missing or bad file leaves the previous rows for that day untouched.

- **Re-running a day:** Clear that day's run in the UI, or use `airflow dags backfill`. It reloads exactly that day's file.
- **`top_pages_weekly`:** It opens the same DuckDB file, so it could collide with a load if the two overlap. Monday 06:00 won't overlap a quick 03:00 load. During the initial backfill, though, a long catchup could still be running then.
- **Sharing one slot:** If you want a hard guarantee, create an Airflow pool with one slot. Then give both DAGs' tasks `pool=` pointing at it. I didn't add that, since it needs the pool created outside the code.