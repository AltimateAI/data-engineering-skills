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
  AND order_ts >= TIMESTAMP '{{ data_interval_start.strftime("%Y-%m-%d %H:%M:%S") }}'
  AND order_ts <  TIMESTAMP '{{ data_interval_end.strftime("%Y-%m-%d %H:%M:%S") }}'
GROUP BY region
ORDER BY region
