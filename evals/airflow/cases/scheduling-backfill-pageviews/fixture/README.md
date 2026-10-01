# web-analytics

Airflow 3.3 project for the marketing site analytics. Everything lands in a
single local DuckDB file, `warehouse/web.duckdb`.

| DAG | What it does |
|---|---|
| `pageviews_daily` | Aggregates one day of raw page views into `daily_pageviews` |
| `top_pages_weekly` | Exports the week's top pages to `exports/top_pages.csv` |

Raw exports: `data/pageviews/<YYYY-MM-DD>.csv` (UTC day, columns
`event_ts, visitor_id, page, referrer`). The web tier writes each file at about
01:00 UTC the following morning.

`daily_pageviews(view_date, page, views, unique_visitors)` feeds the marketing
dashboard. Do not rename it or its columns.

DuckDB allows a single writer per file: two tasks writing `web.duckdb` at the
same time fail with a lock error.
