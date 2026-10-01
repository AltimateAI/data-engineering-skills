```sql
SELECT c.region, SUM(o.amount)
FROM raw.orders o
JOIN raw.customers c ON o.customer_id = c.id
WHERE o.ordered_at >= DATEADD(day, -30, CURRENT_DATE)
GROUP BY 1
ORDER BY 2 DESC
```

The one change is dropping the function wrapper on the filter column. Wrapping `ordered_at` in a date conversion forces Snowflake to evaluate it on every row and blocks micro-partition pruning, so the whole orders table gets scanned. Comparing the raw column to the date boundary lets Snowflake skip every partition older than 30 days, which is usually the difference between minutes and seconds on a large orders table.

The results are identical. A timestamp is on or after the cutoff date exactly when its date part is on or after that date, because the date boundary is implicitly midnight.

Two things to check on your side:

- **Column type.** This assumes `ordered_at` is a DATE or TIMESTAMP. If it is stored as a string, the original conversion was doing real parsing and the rewrite would compare text, so keep the original and fix the column type instead.
- **Clustering.** Pruning only helps if orders data is physically ordered by load time, which is typical for append-only raw tables. If the query is still slow after this change, look at the query profile for partitions scanned versus total, and consider clustering orders on `ordered_at`.