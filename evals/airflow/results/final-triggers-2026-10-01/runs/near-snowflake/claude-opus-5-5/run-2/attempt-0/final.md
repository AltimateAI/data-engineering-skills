The main problem is `TO_DATE(o.ordered_at)` in the `WHERE` clause. Snowflake can only skip micro-partitions using min/max values stored on the raw column. Wrapping the column in a function stops it from doing that, so the query reads every partition of `raw.orders`. Comparing the raw column to the same cutoff date gives the same rows and lets Snowflake skip partitions:

```sql
SELECT c.region, SUM(o.amount)
FROM raw.orders o
JOIN raw.customers c ON o.customer_id = c.id
WHERE o.ordered_at >= DATEADD(day, -30, CURRENT_DATE)
GROUP BY 1
ORDER BY 2 DESC
```

**Why the results are the same:** if `ordered_at` is a `TIMESTAMP_NTZ`, `TIMESTAMP_LTZ` or `DATE`, then `TO_DATE(ordered_at) >= D` matches exactly the rows where `ordered_at >= D 00:00:00`.

**Check these first. I couldn't confirm them because I don't have access to your warehouse:**
- **Column type:** if `ordered_at` is a `VARCHAR`, the rewrite would compare text instead of dates, so don't use it. Fix the column type first. If it's a `TIMESTAMP_TZ`, results can shift slightly at the cutoff when the stored time zones differ from your session's time zone.
- **Clustering:** skipping partitions only helps if `raw.orders` is roughly ordered by `ordered_at`. That's usually true when data is loaded over time. If it isn't, consider a clustering key: `ALTER TABLE raw.orders CLUSTER BY (TO_DATE(ordered_at));`
- **Measuring it:** in the Query Profile, compare "Partitions scanned" with "Partitions total" before and after. If the scan is already small and the time is going to the join or a spill to disk, the next steps are a bigger warehouse or a pre-aggregated table (for example a daily orders rollup).