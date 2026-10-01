I added the `inventory_snapshot` DAG in `dags/inventory_snapshot.py`. A local test run for 2026-09-15 succeeded, and the stock totals matched a separate calculation from the CSV.

**How it works:** the task order is `start >> snapshot >> low_stock`, built the same way as `sales_daily` (same imports, folder layout, `owner`, retries, and one file per `{{ ds }}`).
- **`snapshot`** adds up `qty_change` for every movement dated on or before the run's date. It writes `output/inventory_snapshot/<ds>.csv` (`warehouse_id,sku,on_hand`), sorted by warehouse then SKU. The cutoff matters: the CSV already has movements dated 2026-10-02 and 10-03, and they're left out of earlier dates.
- **`low_stock`** reads the snapshot file and keeps rows where `on_hand` is strictly below the SKU's `reorder_point`. It writes `output/low_stock/<ds>.csv` in the same order. A stock level equal to the reorder point doesn't count as low: on 2026-09-15, LON1 / SKU-001 is at exactly 25 and isn't listed.
- **Schedule:** `"30 2 * * *"`, with `start_date=2026-09-01 UTC` and `catchup=False`. Deploying it won't backfill old dates, but you can rerun any date from 2026-09-01 by clearing it or running `airflow dags backfill`. Each run rewrites both files in full, so reruns just overwrite that day.

**Result for 2026-09-15:** 24 snapshot rows and 4 low-stock rows (BER2/SKU-002, BER2/SKU-004, LON1/SKU-005, LON1/SKU-007).

**Decision for you:** the DAG uses `ds`, as `sales_daily` does. In Airflow 2, that means the run at 02:30 on 2026-10-01 is the 2026-09-30 run and writes the 09-30 files, so each run covers the previous day. I think that's what you want for an end-of-day snapshot. If you'd rather the 02:30 run on day D wrote D's files, say so and I'll switch it.

I deleted the temporary Airflow home and test outputs, so the only change is the new DAG file. It isn't committed.