# logistics-pipelines

| DAG | Schedule | What it does |
|---|---|---|
| `ingest_shipments` | hourly | Appends every carrier event received since the last load to `output/warehouse/shipments/batch_<interval end>.csv`, then updates the `shipments` dataset |
| `carrier_scorecard` | on `shipments` updates | Rebuilds `output/scorecard/carrier_scorecard.csv` from all batches and writes `output/scorecard/_READY` for the ops dashboard |

`data/carrier_events.csv` stands in for the carrier API export (timestamps are
UTC). Every event must be loaded exactly once: the ops team reconciles batch
row counts against the carrier's invoices.
