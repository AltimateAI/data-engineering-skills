I added `dags/daily_revenue.py`, and a local test run for 2026-09-29 03:00 UTC wrote `output/daily_revenue/2026-09-28.csv`. Its totals match an independent pandas check on the 28th: S01 7 orders / 1088.11, S02 9 / 1319.12, S03 7 / 1011.68, S04 9 / 1065.68. I didn't run it twice and compare the files.

- **Schedule:** it runs at `0 3 * * *` UTC. In Airflow 3 a plain cron schedule's logical date is the moment the run starts, so the task takes that date's midnight minus one day as the reported day. A run at 03:00 on the 29th reports on the 28th.
- **Window:** it counts orders from midnight up to, but not including, the next midnight UTC. The file is named after the reported day.
- **Output:** columns are `store_id,orders,revenue`, sorted by `store_id`, with revenue rounded to 2 decimals. A store with no orders that day gets no row.
- **Reruns:** each run overwrites the day's file through a temp file and rename. The result depends only on the logical date and the CSV, so a rerun gives the same file as long as `orders.csv` hasn't changed. Clearing a run or a backfill redoes the same reported day.
- **Start date:** `start_date` is 2026-09-02, because the run on 09-02 reports 09-01. That makes 09-01 the earliest day you can rerun. `catchup` is off, so earlier days only get produced if you backfill or trigger them.

Two things to know:
- `orders.csv` currently starts on 2026-09-20, so earlier days will produce files with only the header row.
- A manually triggered run reports on the day before its logical date, the same as scheduled runs.

I ran the test against a throwaway Airflow database inside the repo and deleted it afterwards. `output/` is gitignored, so the test file isn't in your working tree changes. I haven't committed anything.