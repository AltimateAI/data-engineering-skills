I added `dags/inventory_snapshot.py`. I ran it once with `airflow dags test inventory_snapshot 2026-09-15`, and it succeeded. That run's snapshot and low-stock files look right, but I didn't check the totals by hand.

- **Schedule:** it runs daily at `30 2 * * *` UTC, with `start_date` 2026-09-01 and `catchup=False`. It won't backfill when deployed, and you can still clear or trigger any date from 2026-09-01 on.
- **Snapshot:** the first task sums `qty_change` per warehouse and SKU for every movement dated on or before `ds`. It writes `output/inventory_snapshot/<ds>.csv` with `warehouse_id,sku,on_hand`, sorted by warehouse then SKU.
- **Low stock:** the second task runs after the first. It reads the snapshot file and keeps rows where `on_hand` is below the SKU's reorder point. It writes `output/low_stock/<ds>.csv` with `warehouse_id,sku,on_hand,reorder_point`, sorted the same way.
- **Existing DAG:** it follows `sales_daily`'s conventions: same owner and retries, `ds`-named output files that a rerun overwrites, and the same TaskFlow structure.

- **Missing reorder points:** a SKU with no entry in `reorder_points.csv` is skipped in the low-stock file. Every SKU in the current data has an entry, so this doesn't affect today's output.
- **Which date gets processed:** with a 02:30 schedule, the run that fires on a given morning processes the previous day. Its `ds` is the date of the interval it covers. That matches how `sales_daily` behaves.
- **Output files:** `output/` is gitignored, so the files from my test run won't show up in git.