I added `dags/inventory_snapshot.py`, and it runs correctly. `airflow dags test inventory_snapshot 2026-09-15` succeeded on Airflow 2.11.2, which is the version pinned in `requirements.txt`. The snapshot matches an independent recomputation (24 warehouse/SKU rows). Running the same date a second time gave byte-identical output files. `airflow_check.py` exited 0 with no warnings.

**How it behaves**
- **Schedule:** `30 2 * * *` in UTC, following `sales_daily`. Each run uses `{{ ds }}` as its date, as the existing DAG does, and Airflow 2.x fires at the end of the interval. So the run for date D fires at 02:30 UTC on D+1, once D is complete. The first run is for 2026-09-01, which fires on 2026-09-02 at 02:30.
- **Task 1, `snapshot`:** sums `qty_change` over all movements with `movement_date <= ds`. It writes `output/inventory_snapshot/<ds>.csv` (`warehouse_id,sku,on_hand`), sorted by warehouse then SKU.
- **Task 2, `low_stock`:** runs after the snapshot and reads that file. It writes `output/low_stock/<ds>.csv` with the rows where `on_hand` is below the SKU's reorder point, sorted the same way. A SKU with no entry in `reorder_points.csv` is never flagged. All 8 SKUs currently have one.
- **Reruns and backfill:** `start_date` is 2026-09-01 and `catchup=False`, so deploying doesn't backfill. Any date since 2026-09-01 can be re-run by clearing the run or with `airflow dags backfill`. Each task writes its whole file under a temp name and renames it, so a rerun replaces the file.

For 2026-09-15 the low-stock report lists four rows: BER2/SKU-002, BER2/SKU-004, LON1/SKU-005 and LON1/SKU-007.

**Not verified**
- I didn't run it under a real scheduler, only `dags test`.
- The test files under `output/` are gitignored, so `git status` shows only the new DAG file.