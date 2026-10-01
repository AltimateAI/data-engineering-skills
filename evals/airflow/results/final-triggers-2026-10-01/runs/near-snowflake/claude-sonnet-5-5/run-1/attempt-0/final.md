SELECT c.region, SUM(o.amount)
FROM raw.orders o
JOIN raw.customers c ON o.customer_id = c.id
WHERE o.ordered_at >= DATEADD(day, -30, CURRENT_DATE)
GROUP BY 1
ORDER BY 2 DESC