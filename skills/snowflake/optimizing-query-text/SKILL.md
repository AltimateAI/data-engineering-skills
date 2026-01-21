---
name: optimizing-query-text
description: |
  Optimizes Snowflake SQL query performance from provided query text. Use when optimizing Snowflake SQL for:
  (1) User provides or pastes a SQL query and asks to optimize, tune, or improve it
  (2) Task mentions "slow query", "make faster", "improve performance", "optimize SQL", or "query tuning"
  (3) Reviewing SQL for performance anti-patterns (SELECT *, function on filter column, etc.)
  (4) User asks why a query is slow or how to speed it up
  Analyzes EXPLAIN plan, applies optimization patterns, returns improved SQL with changes summary.
---

# Optimize Query from SQL Text

**Get explain plan → Apply best practices → Verify improvement → Return optimized query**

## Workflow

### 1. Get Explain Plan for Original Query

```sql
EXPLAIN USING JSON
<original_query>;
```

Save the explain plan output. Note key metrics:
- `totalPartitions` vs `assignedPartitions` (partition pruning)
- `rowsProduced` at each step
- Join types and order

### 2. Identify Optimization Opportunities

Review the query for common issues:

| Pattern | Issue | Fix |
|---------|-------|-----|
| `SELECT *` | Scans all columns | Select only needed columns |
| `WHERE DATE(col) = '...'` | Function prevents pruning | Use range: `col >= '...' AND col < '...'` |
| `WHERE col LIKE '%value%'` | Leading wildcard = full scan | Use `col LIKE 'value%'` if possible |
| `OR` across columns | May prevent index use | Rewrite as `UNION ALL` |
| Large table joined first | Memory pressure | Filter early with CTE |
| Repeated subquery | Multiple scans | Use CTE |
| `DISTINCT` on many columns | Expensive | Check if needed, or use `GROUP BY` |
| `ORDER BY` without `LIMIT` | Sorts entire result | Add `LIMIT` or remove if not needed |

### 3. Apply Optimizations

Rewrite the query following these principles:
- Select only needed columns
- Filter early (before joins)
- Use CTEs to avoid repeated scans
- Ensure filter columns match clustering keys
- Push predicates into subqueries

### 4. Get Explain Plan for Optimized Query

```sql
EXPLAIN USING JSON
<optimized_query>;
```

### 5. Compare and Verify

Compare the two explain plans:
- Are fewer partitions scanned?
- Are fewer rows produced at intermediate steps?
- Is the join order improved?

If the optimized query is NOT better, reconsider the approach.

### 6. Return Results

Provide:
1. The optimized query
2. Summary of changes made
3. Expected improvement based on explain plan comparison

## Example

**Original:**
```sql
SELECT * FROM orders o
JOIN customers c ON o.customer_id = c.id
WHERE DATE(o.created_at) = '2024-01-01';
```

**Optimized:**
```sql
WITH filtered_orders AS (
    SELECT order_id, customer_id, amount, created_at
    FROM orders
    WHERE created_at >= '2024-01-01'
      AND created_at < '2024-01-02'
)
SELECT fo.order_id, fo.amount, fo.created_at, c.name, c.email
FROM filtered_orders fo
JOIN customers c ON fo.customer_id = c.id;
```

**Changes:**
- Replaced `SELECT *` with specific columns
- Replaced `DATE()` function with range filter for partition pruning
- Used CTE to filter before join
