I added `dags/daily_revenue.py`. A test run on the 22nd at 03:00 wrote `output/daily_revenue/2026-09-21.csv`, and its figures match an independent `awk` tally of the 21st in `orders.csv`. I tested one day only, not a rerun of the same day or a backfill. I deleted the test output and the scratch Airflow setup afterwards, so nothing but the DAG file is left in the repo.

- **Schedule:** it runs at `0 3 * * *` in UTC. The run at 03:00 on day N reports on day N−1, from midnight to midnight UTC.
- **Which day it reports:** the day comes from the run's scheduled time, not the wall clock. A rerun or backfill of the 29th's 03:00 run therefore always rebuilds the 28th.
- **Output:** each day goes to `output/daily_revenue/<YYYY-MM-DD>.csv`, named after the reported day. The columns are `store_id,orders,revenue`, sorted by `store_id`, with revenue rounded to 2 decimals.
- **Rerun safety:** revenue is summed as exact decimals, so there are no float rounding differences. The file is written to a temp name and then renamed over the old one, so a rerun cleanly overwrites it with identical content.
- **Rerunning from 2026-09-01:** I set the DAG's start date to 2026-09-02. The 09-02 03:00 run is the first to report on 09-01, and a start date of 09-01 would add a run reporting on 08-31. Earlier runs will not fire on their own because `catchup=False`, which matches `store_dimension`. To rebuild any day, trigger a backfill for that day's 03:00 run.
- **Timestamps:** `order_ts` is treated as UTC. The CSV has no timezone, so tell me if it is actually in local time.
- **No pandas:** I used the standard `csv` module rather than pandas.

I did not commit anything.