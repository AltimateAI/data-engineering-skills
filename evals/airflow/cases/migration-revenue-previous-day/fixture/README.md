# finance-pipelines

Airflow DAGs for the finance team.

| DAG | Schedule | What it does |
|---|---|---|
| `daily_revenue` | 04:15 UTC daily | Completed-order revenue per region for the previous UTC business day, written to `output/daily_revenue/<business_date>.csv`, plus `output/manifests/<business_date>.json` for the dashboard |
| `region_reference` | manual | Rebuilds `output/reference/regions.csv` |

Local checks:

```bash
pytest tests/
airflow dags test daily_revenue 2026-03-04
```
