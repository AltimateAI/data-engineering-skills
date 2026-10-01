The main problem is that the filter wraps `ordered_at` in `TO_DATE()`. Because of that, Snowflake can't use the column's min/max metadata to skip micro-partitions, so it scans all of `raw.orders`. If you compare the raw column directly, Snowflake can skip every partition older than 30 days:

```sql
SELECT c.region, SUM(o.amount)
FROM raw.orders o
JOIN raw.customers c ON o.customer_id = c.id
WHERE o.ordered_at >= DATEADD(day, -30, CURRENT_DATE)
GROUP BY 1
ORDER BY 2 DESC
```

It returns the same rows: `TO_DATE(ts) >= D` is true exactly when `ts >= D 00:00:00`.

I haven't run this against your warehouse, so I can't confirm the speedup. Three things affect it:

- **Column type:** the rewrite is exact if `ordered_at` is a `TIMESTAMP_NTZ`, `TIMESTAMP_LTZ` or `DATE`. If it's a `TIMESTAMP_TZ` stored in a different offset from your session, rows near midnight on the cutoff day could be counted differently.
- **String column:** if `ordered_at` is stored as text, pruning won't help. You'd need to change it to a real timestamp column first.
- **Table clustering:** the gain depends on `raw.orders` being roughly ordered by `ordered_at`, which is usually true if it's loaded in time order. To check, run `SELECT SYSTEM$CLUSTERING_INFORMATION('raw.orders', '(ordered_at)')`, or compare "Partitions scanned" with "Partitions total" in the query profile. If the data isn't ordered that way, add a clustering key on `ordered_at` (or `TO_DATE(ordered_at)`).