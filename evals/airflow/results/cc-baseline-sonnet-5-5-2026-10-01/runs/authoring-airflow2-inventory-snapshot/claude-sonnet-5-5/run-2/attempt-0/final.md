I added `dags/inventory_snapshot.py`. I ran it with `airflow dags test inventory_snapshot 2026-09-15` and both tasks succeeded. The snapshot file had the right columns and sort order, and the low-stock file listed 4 rows (BER2 and LON1). I deleted the test outputs afterwards and didn't check the numbers against the raw CSV by hand.

- **Schedule:** it runs at `30 2 * * *` (02:30 UTC) with `start_date` 2026-09-01 and `catchup=False`, so deploying it won't backfill. Any date from 2026-09-01 on can still be rerun by clearing or triggering it.
- **Snapshot task:** `on_hand` is the sum of `qty_change` for every movement dated on or before the run's `ds`. It writes `output/inventory_snapshot/<ds>.csv` as `warehouse_id,sku,on_hand`, sorted by warehouse then SKU.
- **Low-stock task:** it runs after the snapshot and writes `output/low_stock/<ds>.csv` as `warehouse_id,sku,on_hand,reorder_point`. It keeps rows where `on_hand` is below the SKU's reorder point, sorted the same way. A SKU with no entry in `reorder_points.csv` is never flagged.
- **Consistency with `sales_daily`:** it uses the same `@dag`/`@task` style, `ds`-named files, owner, retry settings and plain `csv` module. Reruns overwrite that day's files.

A warehouse/SKU pair with no movements up to the date doesn't appear in the snapshot at all, rather than showing as 0. It also can't be flagged as low stock.

Airflow's `{{ ds }}` is the start of the data interval, so the run that fires at 02:30 UTC on the 16th has `ds` = 2026-09-15. Its files are therefore stamped with the 15th and cover movements through the 15th. That matches how `sales_daily` behaves.