# shop-analytics

Airflow 2.11 project that loads the shop's order exports into a local DuckDB
warehouse (`warehouse/analytics.duckdb`).

| DAG | What it does |
|---|---|
| `orders_daily_load` | Loads the previous day's orders into `orders`, then refreshes `daily_revenue` |
| `customers_snapshot` | Full refresh of the `customers` dimension |

Tables read by the finance dashboard (do not change their columns):

- `orders(order_id, order_date, customer_id, amount_usd, loaded_at)`
- `daily_revenue(order_date, order_count, revenue_usd)`

Local run: `airflow dags test orders_daily_load 2026-03-10`
