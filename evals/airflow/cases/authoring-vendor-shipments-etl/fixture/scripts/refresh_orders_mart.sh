#!/usr/bin/env bash
# Rebuild the orders mart for one day. Usage: refresh_orders_mart.sh YYYY-MM-DD
set -euo pipefail
DAY="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python - "$ROOT/warehouse/analytics.duckdb" "$DAY" <<'PY'
import sys, duckdb
db, day = sys.argv[1], sys.argv[2]
with duckdb.connect(db) as con:
    con.execute("CREATE TABLE IF NOT EXISTS orders_mart (order_date DATE, orders BIGINT, revenue DOUBLE)")
    con.execute("DELETE FROM orders_mart WHERE order_date = CAST(? AS DATE)", [day])
    con.execute("INSERT INTO orders_mart SELECT order_date, count(*), sum(amount) FROM orders "
                "WHERE order_date = CAST(? AS DATE) GROUP BY order_date", [day])
PY
echo "orders mart refreshed for $DAY"
