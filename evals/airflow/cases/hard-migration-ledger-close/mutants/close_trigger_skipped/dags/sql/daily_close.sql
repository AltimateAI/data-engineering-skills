{%- set start, end = close_window(dag_run) -%}
{%- if start is none %}{% set start, end = dag_run.run_after, dag_run.run_after %}{% endif -%}
-- Net movement per account for business day {{ start | ds }}
-- (fiscal period {{ macros.ledger.fiscal_period(start | ds) }}).
SELECT
    account,
    '{{ macros.ledger.fiscal_period(start | ds) }}' AS fiscal_period,
    CAST(SUM(CAST(amount_cents AS BIGINT)) AS BIGINT) AS net_cents,
    COUNT(*) AS postings
FROM read_csv('{{ params.postings }}', header = true, all_varchar = true)
WHERE booked_at >= '{{ start.strftime("%Y-%m-%d %H:%M:%S") }}'
  AND booked_at <  '{{ end.strftime("%Y-%m-%d %H:%M:%S") }}'
GROUP BY account
ORDER BY account
