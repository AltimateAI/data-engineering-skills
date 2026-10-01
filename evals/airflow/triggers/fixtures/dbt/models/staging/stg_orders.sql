select
    id as order_id,
    customer_id,
    ordered_at,
    amount
from {{ source('shop', 'orders') }}
