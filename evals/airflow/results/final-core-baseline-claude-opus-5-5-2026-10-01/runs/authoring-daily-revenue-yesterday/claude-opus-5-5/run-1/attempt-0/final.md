I added the `daily_revenue` DAG in `dags/daily_revenue.py`. It runs every day at 03:00 UTC and writes `output/daily_revenue/<YYYY-MM-DD>.csv` for the previous calendar day (UTC, midnight to midnight). I ran it locally with `airflow dags test` and it works.

**How it decides which day to report:** I set the schedule to fire at exactly 03:00 UTC, so a run's "logical date" is its start time. The report day is that date minus one, so the 03:00 run on the 29th reports on the 28th. Manual and rerun triggers follow the same rule.

**Test results:**
- **The run for the 29th** wrote `2026-09-28.csv`:
  ```
  store_id,orders,revenue
  S01,7,1088.11
  S02,9,1319.12
  S03,7,1011.68
  S04,9,1065.68
  ```
  These numbers match a separate tally I did straight from `orders.csv`.
- **Reruns:** running the same day again produced a byte-identical file. Each run rewrites the whole file and swaps it in all at once, so finance never sees a half-written file.
- **Rounding:** revenue is added up with exact decimal arithmetic and rounded to 2 decimals.

**Earlier days:** the first scheduled run is 2026-09-02 at 03:00, which reports on 2026-09-01, so any day from then on can be rerun. I set `catchup=False` to match `store_dimension`, so turning the DAG on won't automatically fill in past days. To produce September's earlier files, use `airflow backfill create` or `airflow dags test daily_revenue <run date>`.

**Decisions for you:**
- **Stores with no orders** are left out of that day's file rather than listed with 0 orders and 0.00 revenue. If finance wants every store from `stores.csv` on every day, that's a small change.
- **2026-09-01 to 2026-09-19 will come out empty.** `data/orders.csv` currently only goes back to 2026-09-20, so those files will have just the header row. They'll fill in only if the export contains orders for those days.

I haven't committed anything.