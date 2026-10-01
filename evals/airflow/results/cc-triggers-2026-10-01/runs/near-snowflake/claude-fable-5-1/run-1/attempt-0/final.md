```sql
SELECT c.region, SUM(o.amount)
FROM raw.orders o
JOIN raw.customers c ON o.customer_id = c.id
WHERE o.ordered_at >= DATEADD(day, -30, CURRENT_DATE)
GROUP BY 1
ORDER BY 2 DESC
```

The only change is dropping the `TO_DATE()` wrapper on the filter column. Wrapping the column in a function forces Snowflake to scan every micro-partition of orders. Comparing the raw column against the date lets it prune partitions by the `ordered_at` min/max metadata. The results are identical as long as `ordered_at` is a DATE or TIMESTAMP column, since truncating to a date and comparing to midnight gives the same rows. If `ordered_at` is stored as a string, keep the original query.

If this is still slow after the change, the next step is to check that orders is clustered on `ordered_at`, since pruning only helps when the partitions are well-ordered by that column.