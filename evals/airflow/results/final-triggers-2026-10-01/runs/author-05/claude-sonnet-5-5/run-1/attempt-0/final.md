I changed `dags/events_load.py` so each run replaces its own hourly slice of `analytics.events` instead of appending. I haven't run or tested it. The task body is still a stub that prints and describes the SQL, as the original did.

- **Cause of the duplicates:** the old job selected `raw.events WHERE loaded = false` and appended. Rerunning a run, or backfilling, re-selected rows that were already inserted.
- **Fix:** each run now uses its `data_interval_start` and `data_interval_end`. In one transaction it deletes that window from `analytics.events`, then inserts the same window from `raw.events`. Rerunning any interval gives the same result.
- **Backfill:** backfill by date range with `airflow backfill create --from-date … --to-date …`. I left `catchup=False` so deploying doesn't trigger a flood of runs. I also added `max_active_runs=1` so overlapping runs can't touch the same window.

Things to check:
- I assumed an `event_ts` column on both tables. If the real column has a different name, change it in the SQL.
- The DELETE and INSERT need to run in one transaction against your warehouse. When you wire in the real connection, use a single transaction or a `MERGE` on the event ID.
- The window is by event time. Events that arrive late with an old `event_ts` will only be picked up when you rerun that interval.