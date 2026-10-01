# logistics-pipelines

Airflow 2.11 DAGs for the logistics ops team. We are staying on 2.11 until the
platform upgrade next year.

- `dags/shipments_daily.py` - weekday late-shipment exceptions report
  (`output/late_shipments/<ds>.csv`).
- `dags/carrier_rates_weekly.py` - weekly average freight rate per carrier.
- `data/` - sample exports used in dev.

Local run:

```bash
pip install -r requirements.txt
airflow dags test shipments_daily 2026-03-03
```
