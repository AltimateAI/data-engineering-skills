-- Completed-order revenue per region for one UTC business day.
SELECT
    region,
    COUNT(*) AS orders,
    CAST(SUM(amount) AS DOUBLE) AS revenue
FROM read_csv(
    '{{ params.orders_path }}',
    header = true,
    columns = {
        'order_id': 'VARCHAR',
        'order_ts': 'TIMESTAMP',
        'region': 'VARCHAR',
        'amount': 'DECIMAL(12, 2)',
        'status': 'VARCHAR'
    }
)
WHERE status = 'completed'
  AND order_ts >= TIMESTAMP '{{ ds }} 00:00:00'
  AND order_ts <  TIMESTAMP '{{ next_ds }} 00:00:00'
GROUP BY region
ORDER BY region
