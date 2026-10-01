I added the `inventory_snapshot` DAG in `dags/inventory_snapshot.py`, modelled on `sales_daily`. I couldn't run it through the Airflow scheduler because the local Airflow database isn't initialised. Instead I called the two task functions directly for 2026-09-15 and checked the output.

- **Schedule:** it runs at `30 2 * * *` in UTC.
- **Reruns and backfill:** `start_date` is 2026-09-01 and `catchup=False`. Nothing backfills on deploy, but any date since 2026-09-01 can be cleared in the UI or run with `airflow dags backfill`. Each run overwrites that date's files.
- **`snapshot` task:** it sums `qty_change` per warehouse and SKU over every movement dated on or before the run date. It writes `output/inventory_snapshot/<date>.csv` with `warehouse_id,sku,on_hand`, sorted by warehouse then SKU.
- **`low_stock` task:** it runs after `snapshot`, reads that file, and keeps rows where `on_hand` is below the SKU's reorder point. It writes `output/low_stock/<date>.csv` with `warehouse_id,sku,on_hand,reorder_point`, sorted the same way.

**Test run:** for 2026-09-15 it produced four low-stock rows (BER2/SKU-002, BER2/SKU-004, LON1/SKU-005, LON1/SKU-007). `output/` is gitignored, so I left those test files uncommitted.

A SKU with no entry in `reorder_points.csv` is never flagged as low stock. Every SKU in the current data has a reorder point.