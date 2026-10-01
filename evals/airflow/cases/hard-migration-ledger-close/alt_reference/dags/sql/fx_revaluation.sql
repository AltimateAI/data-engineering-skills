-- Revalue everything booked up to the end of {{ ds }} at that day's rate (published the
-- morning of {{ macros.ds_add(ds, 1) }}), in {{ base_currency() }}. The previous
-- day's rate ({{ macros.ds_add(ds, -1) }}) gives the day's revaluation effect.
WITH balances AS (
    SELECT account, currency, SUM(CAST(amount_cents AS BIGINT)) AS amount_cents
    FROM read_csv('{{ params.data_dir }}/postings.csv', header = true, all_varchar = true)
    WHERE booked_at < '{{ macros.ds_add(ds, 1) }} 00:00:00'
    GROUP BY account, currency
),
rates AS (
    SELECT currency, rate_date, CAST(usd_per_unit_e4 AS BIGINT) AS e4
    FROM read_csv('{{ params.data_dir }}/fx_rates.csv', header = true, all_varchar = true)
)
SELECT
    b.account,
    b.currency,
    CAST(b.amount_cents AS BIGINT) AS amount_cents,
    CAST(b.amount_cents * today.e4 // 10000 AS BIGINT) AS base_cents,
    CAST(b.amount_cents * (today.e4 - prev.e4) // 10000 AS BIGINT) AS revaluation_cents,
    '{{ base_currency() }}' AS base_currency
FROM balances b
JOIN rates today ON today.currency = b.currency AND today.rate_date = '{{ ds }}'
JOIN rates prev ON prev.currency = b.currency AND prev.rate_date = '{{ macros.ds_add(ds, -1) }}'
ORDER BY b.account, b.currency
