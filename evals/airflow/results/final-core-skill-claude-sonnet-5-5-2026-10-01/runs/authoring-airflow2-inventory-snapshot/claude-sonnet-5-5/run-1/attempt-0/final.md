I added `dags/inventory_snapshot.py`. It parses cleanly and the two tasks ran successfully for 2026-09-28, but I haven't watched a scheduled tick fire.

**How it works**
- **Schedule:** it runs at `30 2 * * *` in UTC, with `catchup=False` and a fixed `start_date` of 2026-09-01. It won't backfill on deploy.
- **Run date:** it uses `ds`, the same as `sales_daily`. The run at 02:30 on Sep 29 therefore produces the Sep 28 files, which means the day is complete before the snapshot runs.
- **Snapshot task:** it sums `qty_change` for every movement dated on or before `ds`. It writes `output/inventory_snapshot/<ds>.csv` with `warehouse_id,sku,on_hand`, sorted by warehouse then SKU.
- **Low-stock task:** it runs after the snapshot and reads the snapshot file. It writes `output/low_stock/<ds>.csv` with `warehouse_id,sku,on_hand,reorder_point` for rows where `on_hand` is below the reorder point. SKUs with no entry in `reorder_points.csv` are skipped.
- **Reruns:** each file is written in full and swapped into place, so rerunning a date overwrites it. Clearing a run or running `airflow dags backfill` for any date from 2026-09-01 on will reproduce that date's files. The DAG also uses the same `default_args` as `sales_daily` (owner, 1 retry).

**What I ran**
- **Schedule check:** `airflow_check.py` on Airflow 2.11.2 (the version `requirements.txt` pins) exited 0, and the next three runs came out as expected.
- **Test run:** `airflow dags test inventory_snapshot 2026-09-28` succeeded twice. The second run produced the same files.
- **Output check:** the snapshot has 24 rows, and I confirmed it matches an independent sum over the movements. The low-stock file has 3 rows: BER2/SKU-002 (23 vs 55), BER2/SKU-004 (26 vs 45) and LON1/SKU-007 (49 vs 55).

**Not verified:** a real scheduler tick, a `dags backfill` run, and dates other than 2026-09-28. The `output/` files from my test are gitignored. I used a temporary `AIRFLOW_HOME` and deleted it afterwards.

I haven't committed anything.