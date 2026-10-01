# finance-orders

Airflow 3.3 pipeline that enriches the daily orders export with USD amounts for the
finance team.

- `dags/orders_enrichment.py` - extract, dedupe, FX-convert, validate and publish
  `output/orders_enriched/<ds>.csv`.
- `data/` - sample exports (orders and daily FX rates) used in dev.

Local run:

```bash
pip install -r requirements.txt
airflow dags test orders_enrichment 2026-03-02
```
