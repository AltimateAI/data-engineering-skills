A **DAG** is a **Directed Acyclic Graph**: a set of nodes connected by arrows, where the arrows have a direction and you can never follow them in a loop back to where you started.

- **Directed**: each edge points one way (A → B means "A comes before B").
- **Acyclic**: no cycles. You can't have A → B → C → A.
- **Graph**: nodes (steps) and edges (dependencies).

**Why data engineers talk about them**

A data pipeline is really a set of steps with dependencies: extract the data, clean it, join it with another table, build a report. Some steps can't start until others finish, and some can run in parallel. A DAG models this directly.

1. **Execution order**: a scheduler can topologically sort the graph to work out what runs when, and run independent branches in parallel.
2. **No infinite loops**: the "acyclic" rule guarantees every pipeline has a start and an end. A cycle would mean step A waits on itself.
3. **Targeted failure and retry**: if one task fails, you know exactly which downstream tasks to hold back and which upstream ones are already done. You can re-run just the failed part instead of the whole pipeline.
4. **Lineage and impact analysis**: you can trace where a column or table came from, and what would break downstream if you change it.
5. **Visualization**: the graph is easy to draw and reason about, which helps with debugging and onboarding.

**Where you'll see them**

- **Airflow, Dagster, Prefect**: orchestrators where you define pipelines as DAGs. Airflow literally calls each pipeline a "DAG".
- **dbt**: models reference each other with `ref()`, and dbt builds a DAG from those references to decide build order.
- **Spark**: jobs are compiled into a DAG of stages internally.

**Tiny example**

```
extract_orders ─┐
                ├─> join_and_clean ─> build_report
extract_users ──┘
```

The two extracts can run in parallel. The join waits for both. The report waits for the join. There's no path leading back, so it's a valid DAG.