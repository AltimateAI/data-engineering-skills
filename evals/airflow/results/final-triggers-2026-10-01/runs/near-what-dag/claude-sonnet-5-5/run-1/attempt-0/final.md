A **DAG** is a **Directed Acyclic Graph**: a set of nodes connected by arrows, where the arrows have a direction and you can never follow them in a loop back to where you started.

- **Directed**: each edge points one way (A → B means "A comes before B").
- **Acyclic**: no cycles. You can't have A → B → C → A.
- **Graph**: nodes (steps) and edges (dependencies).

## Why data engineers care

Data pipelines are naturally this shape. You have tasks like "extract orders," "clean orders," "join with customers," and "build the revenue table." Some must finish before others can start, and some are independent of each other. A DAG captures that.

1. **Dependency ordering**: The "directed" part tells the scheduler what has to run first. You can't build the revenue table until the join is done.
2. **Parallelism**: Tasks with no dependency between them (like extracting orders and extracting customers) can run at the same time.
3. **No infinite loops**: The "acyclic" part guarantees the pipeline can finish. If A waited on B and B waited on A, nothing would ever run.
4. **Retries and backfills**: If one task fails, you rerun it and everything downstream of it, not the whole pipeline.
5. **Lineage and impact analysis**: The graph shows where data came from and what breaks downstream if you change something.
6. **Visibility**: Orchestrators can draw the graph, so you can see what's running, what failed, and what's blocked.

## Where you see them

- **Airflow, Dagster, Prefect**: you define your pipeline as a DAG (in Airflow, literally a `DAG` object).
- **dbt**: models that `ref()` each other form a DAG, and dbt builds them in dependency order.
- **Spark**: jobs compile into a DAG of stages internally.
- **Git**: commit history is also a DAG, so it's a general idea beyond data work.

In short, a DAG is the way to say "do these things in this order, in parallel where possible, and never in circles."