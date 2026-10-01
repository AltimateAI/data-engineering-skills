# warehouse-ops

Airflow pipelines for the fulfilment centre.

- `dags/inventory_snapshot.py`: nightly stock-on-hand snapshot per SKU and the
  audit record used by replenishment alerting.
- `data/stock_movements.csv`: movement ledger export (receipts are positive,
  shipments negative, timestamps in UTC).

Outputs land in `output/` (git-ignored).
