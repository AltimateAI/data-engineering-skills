A **DAG** is a **Directed Acyclic Graph**:

- **Graph**: a set of nodes (tasks) joined by edges (dependencies).
- **Directed**: every edge points one way. "A → B" means B depends on A, so A runs first.
- **Acyclic**: no loops. You can't follow the arrows and end up back where you started.

```
extract_orders ──┐
                 ├──► join_orders_customers ──► build_revenue_report
extract_customers┘
```

### Why data engineers talk about them so much

Almost every data pipeline is a set of steps where some steps need others to finish first. A DAG is the natural way to describe that, and it brings several practical benefits:

1. **Execution order comes for free.** Because there are no cycles, the graph can always be put in a valid run order (a "topological sort"). You declare the dependencies and the tool works out the order.
2. **Parallelism.** Tasks that don't depend on each other, like the two extracts above, can run at the same time.
3. **Failure handling and reruns.** If `join_orders_customers` fails, the scheduler knows not to run anything downstream of it. Once you fix it, you can rerun just that task and what comes after it, not the whole pipeline.
4. **Lineage and impact analysis.** You can ask "if I change this table, what breaks downstream?" and answer it by walking the graph.
5. **No circular dependencies.** If A needs B and B needs A, neither can ever run. The "acyclic" rule prevents that by design.

### Where you'll see them

- **Airflow, Dagster, Prefect**: pipelines are literally called DAGs, or defined as them. In Airflow you write a `DAG` object made of tasks.
- **dbt**: every `ref('other_model')` adds an edge. dbt builds the DAG of your models and runs them in dependency order (`dbt build --select my_model+` means "this model and everything downstream").
- **Spark**: it turns your transformations into a DAG of stages before running them.

**In short:** "DAG" is the shared vocabulary for "a set of steps with dependencies and no loops." Nearly every pipeline tool is built on that idea, which is why the term comes up constantly.