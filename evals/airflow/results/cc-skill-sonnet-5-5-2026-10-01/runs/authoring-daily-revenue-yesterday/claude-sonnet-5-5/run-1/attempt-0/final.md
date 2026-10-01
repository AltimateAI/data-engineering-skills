I added the `daily_revenue` DAG in `dags/daily_revenue.py`. A run at 03:00 UTC on the 29th writes `output/daily_revenue/2026-09-28.csv`. I haven't committed anything.

**Schedule**
- It fires daily at 03:00 UTC, and each run reports on the day before the one it fires on, midnight to midnight UTC.
- A manual trigger with no date follows the same rule, based on when it was triggered.
- Clearing or backfilling a run reports the same day as the original run and overwrites its file, so rerunning a day gives an identical file.
- To report on a specific day by hand, set the `day` param (YYYY-MM-DD).
- `start_date` is 2026-09-02, so the first scheduled run reports 2026-09-01. Every day since then can be rerun by clearing or backfilling its run.
- `catchup=False`, so deploying won't backfill history on its own.
- `max_active_runs=1`.

**Output**
- Columns are `store_id,orders,revenue`, sorted by `store_id`.
- Revenue is summed exactly and rounded to 2 decimals.
- A store with no orders that day gets no row. Say if finance wants zero rows for every store in `stores.csv`.

**What I ran**
- `airflow_check.py` exited 0. The next scheduled runs are 09-02, 09-03 and 09-04 at 03:00 UTC. Its one warning, about trigger timetables, doesn't apply because the DAG works out the reported day itself.
- `airflow dags test daily_revenue 2026-09-29T03:00:00+00:00` succeeded and wrote the 09-28 file. The per-store counts and sums match an independent `awk` tally of `orders.csv`. A second run produced a byte-identical file.
- A manual trigger with no logical date at 2026-09-30 03:00Z succeeded and wrote the 09-29 file.

I did not run it under a live scheduler, and I did not test `airflow backfill create`.