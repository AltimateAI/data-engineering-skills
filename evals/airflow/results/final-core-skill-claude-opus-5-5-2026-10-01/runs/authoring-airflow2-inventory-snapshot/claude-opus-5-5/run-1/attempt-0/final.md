I added `dags/inventory_snapshot.py` and ran it for real locally. Both output files match an independent recalculation from the CSVs, and rerunning a date gives identical files.

**How the dates work (Airflow 2.11.2, from `requirements.txt` and the installed environment)**
- The schedule is `30 2 * * *` UTC. Like `sales_daily`, files are named after the run's logical date, `{{ ds }}`. In Airflow 2, a run for date D starts at 02:30 UTC on D+1, after D has ended. So the file for 2026-09-29 is written on 2026-09-30 at 02:30.
- Rerunning a date (clearing a run, or `airflow dags test inventory_snapshot <date>`) rebuilds that date's files and replaces them. Each file is written in full to a temporary name and then renamed, so a retry or rerun never leaves a partly written file.
- `start_date` is 2026-09-01 and `catchup=False`, so any date from 2026-09-01 can be rerun, but deploying it won't backfill the missed dates.

**What it does**
- **Tasks:** it has the same `start` task, owner, retries and path setup as `sales_daily`, then `snapshot` followed by `low_stock`. The only thing passed between them is the snapshot file's path.
- **`snapshot`:** sums `qty_change` over every movement up to and including the run's date. That cutoff matters: `inventory_movements.csv` already contains rows dated up to 2026-10-03, after the dates being reported on.
- **`low_stock`:** keeps rows where `on_hand` is strictly below the SKU's reorder point. A SKU missing from `reorder_points.csv` is never flagged. Today all 8 SKUs have a reorder point.
- Both files are sorted by `warehouse_id` then `sku`.

**Checks I ran**
- **Static check:** the DAG loads with no errors or warnings, and the upcoming runs line up with the dates described above.
- **Real runs:** 2026-09-01 and 2026-09-29 both succeeded. Each snapshot has 24 rows; the low-stock files have 10 and 2 rows. For 2026-09-29 the low-stock rows are BER2/SKU-002 (23 vs 55) and BER2/SKU-004 (12 vs 45).
- **Rerun:** running 2026-09-29 a second time produced byte-identical files.
- **Cleanup:** I deleted the local Airflow database and the `output/` folder these test runs created, so `git status` shows only the new DAG file.

**Not checked:** the managed production Airflow environment, and a retry after a deliberately forced failure.