A **DAG** is a *directed acyclic graph*: a set of nodes connected by arrows (edges), where the arrows have a direction and you can never follow them in a loop back to where you started.

- **Directed**: each edge goes one way, from A to B, meaning "A comes before B" or "B depends on A".
- **Acyclic**: no cycles. A can't depend on B if B (directly or indirectly) depends on A.
- **Graph**: nodes plus edges.

**Why data engineers talk about them constantly:**

A data pipeline is a set of steps with dependencies. For example, you extract raw data, clean it, join it with another table, and then build a report. A DAG is a natural way to describe that.

1. **Execution order.** The graph says what must finish before something else can start. Steps with no dependency between them can run in parallel.
2. **No circular dependencies.** The "acyclic" part guarantees there is a valid order to run things in. A cycle would mean a step waits on itself forever.
3. **Retries and partial reruns.** If one task fails, you only rerun it and whatever is downstream of it, not the whole pipeline.
4. **Lineage and impact analysis.** You can trace where a column or table came from, and what breaks downstream if you change it.
5. **Scheduling and monitoring.** Orchestrators can show you the graph, which tasks succeeded or failed, and where the bottleneck is.

**Where you'll see them:**

- **Airflow**: you literally write "DAGs" in Python. Each DAG is a pipeline made of tasks.
- **dbt**: models reference each other with `ref()`, and dbt builds a DAG from those references to decide build order.
- **Dagster, Prefect, Spark**: all use the same idea, sometimes under different names.

A tiny example:

```
extract_orders ──► clean_orders ──┐
                                  ├──► join ──► daily_report
extract_customers ─► clean_customers ┘
```

The two extract/clean branches can run in parallel, `join` waits for both, and `daily_report` waits for `join`.