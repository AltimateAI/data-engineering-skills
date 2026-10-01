select o.order_id, o.customer_id, c.name as customer_name, o.ordered_at, o.amount
from {{ ref('stg_orders') }} o
left join {{ ref('stg_customers') }} c using (customer_id)
