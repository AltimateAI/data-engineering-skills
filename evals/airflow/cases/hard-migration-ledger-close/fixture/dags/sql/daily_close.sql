-- Net movement per account for business day {{ data_interval_start | ds }}
-- (fiscal period {{ macros.ledger.fiscal_period(data_interval_start | ds) }}).
SELECT
    account,
    '{{ macros.ledger.fiscal_period(data_interval_start | ds) }}' AS fiscal_period,
    CAST(SUM(CAST(amount_cents AS BIGINT)) AS BIGINT) AS net_cents,
    COUNT(*) AS postings
FROM read_csv('{{ params.postings }}', header = true, all_varchar = true)
WHERE booked_at >= '{{ data_interval_start.strftime("%Y-%m-%d %H:%M:%S") }}'
  AND booked_at <  '{{ data_interval_end.strftime("%Y-%m-%d %H:%M:%S") }}'
GROUP BY account
ORDER BY account
