I added the `daily_revenue` DAG in `dags/daily_revenue.py`. It runs every day at 03:00 UTC and writes `output/daily_revenue/<YYYY-MM-DD>.csv` for the previous UTC calendar day. I ran it under the project's Airflow (3.3.2) and the outputs are correct.

**How it works**
- **Which day it reports on:** one helper decides the day, and every kind of run uses it.
  - **Scheduled run:** the run at 03:00 on the 29th reports on the 28th (orders with `2026-09-28 00:00:00 ≤ order_ts < 2026-09-29 00:00:00`).
  - **Manual trigger from the UI:** reports on the day before the trigger time.
  - **Rerun or backfill:** reports on the same day as the original run.
  - **Picking a day directly:** you can trigger with `{"day": "2026-09-05"}`.
- **Rerunning old days:** the start date is 2026-09-01, so any day from then on can be rerun. Missed days are not filled in automatically when the DAG is deployed; you rerun them yourself. For example, `airflow backfill create --dag-id daily_revenue --from-date 2026-09-02T00:00:00+00:00 --to-date 2026-09-30T23:59:00+00:00` produces the files for 09-01 through 09-29. Only one run goes at a time.
- **Reruns give the same file:** each run rebuilds the whole file for its day from `orders.csv` and swaps it in at once (write to a temp file, then rename). It never adds to an existing file, so a rerun also picks up any late orders.
- **Output format:** columns `store_id,orders,revenue`, revenue always shown with 2 decimals, sorted by `store_id`.

**What I ran**
- **Parse check:** the file loads cleanly and the next scheduled runs are at 03:00 UTC each day.
- **Correctness:** `airflow dags test daily_revenue 2026-09-29T03:00:00+00:00` wrote `2026-09-28.csv` (S01 7/1088.11, S02 9/1319.12, S03 7/1011.68, S04 9/1065.68). That matches a separate exact-decimal recount from the CSV.
- **Rerun:** running the same day again produced a byte-identical file.
- **Several runs in a row:** three scheduled runs (09-21 to 09-23) wrote the files for 09-20 to 09-22. A manual trigger at 09-30 10:15 wrote 09-29. A rerun reproduced 09-20. Triggering with `{"day":"2026-09-25"}` wrote 09-25.
- **Cleanup:** I deleted the test outputs and the temporary Airflow files afterwards. Only the new DAG file is left, and it isn't committed.

**Things to know**
- **Days with no data:** `data/orders.csv` currently starts at 2026-09-20. A rerun for an earlier day, such as 09-01, therefore produces a file with only the header row.
- **Stores with no orders:** a store with no orders that day is left out of the file rather than listed with 0 orders. If finance wants every store from `stores.csv` listed with zeros, that's a small change.
- **Not tested:** I didn't test a real scheduler run or the finance tool picking up the files.