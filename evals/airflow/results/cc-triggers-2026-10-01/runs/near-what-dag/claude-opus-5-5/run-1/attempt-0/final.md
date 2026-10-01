**DAG** stands for **Directed Acyclic Graph**:

- **Graph:** a set of nodes (tasks) joined by edges (dependencies).
- **Directed:** each edge points one way. "A → B" means B depends on A, so A runs first.
- **Acyclic:** there are no loops. You can't follow the arrows and end up back where you started, so there's always a valid order to run things in.

```
extract_orders ─┐
                ├─► join_and_clean ─► build_report ─► email_report
extract_users ──┘
```

### Why data engineers talk about them so much

Most data pipelines are a DAG: pull from sources, transform, combine, then publish. Modeling a pipeline this way gives you several things:

1. **Execution order.** The scheduler sorts the graph (a "topological sort") to decide what runs when. You only declare dependencies and never write the sequence by hand.
2. **Parallelism.** Tasks that don't depend on each other can run at the same time. In the example, both `extract_*` tasks run in parallel.
3. **Failure handling.** If `join_and_clean` fails, everything downstream is skipped. Once you fix it, you rerun from that point instead of rerunning the whole pipeline.
4. **Lineage and impact analysis.** The graph tells you what's upstream and downstream of any table. That answers questions like "if I change this column, what breaks?"
5. **No deadlocks.** A cycle would mean "A waits for B, and B waits for A." The "acyclic" rule rules that out.

### Where you'll see the term

- **Apache Airflow:** a pipeline is literally a Python object called a `DAG`, made of tasks.
- **dbt:** models reference each other with `ref()`, and dbt builds a DAG from those references to decide build order. This is the lineage graph in dbt docs.
- **Dagster, Prefect, Spark, Luigi:** each uses a DAG internally to plan its work. Spark, for example, turns your transformations into a DAG of stages.

In short, a DAG is a dependency graph without loops. That's exactly the structure of "do these steps in the right order, in parallel where possible," which is most of what data engineering involves.