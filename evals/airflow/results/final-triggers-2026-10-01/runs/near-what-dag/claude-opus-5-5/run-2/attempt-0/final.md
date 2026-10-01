A **DAG** is a **Directed Acyclic Graph**:

- **Graph**: a set of nodes (tasks) connected by edges (dependencies).
- **Directed**: each edge points one way. "A → B" means B depends on A, so A runs first.
- **Acyclic**: there are no loops. You can't follow the arrows and end up back where you started. A pipeline where A needs B and B needs A could never start.

```
extract_orders ──┐
                 ├──> join_orders_customers ──> build_revenue_report
extract_customers┘
```

### Why data engineers keep bringing them up

1. **They're how pipelines are structured.** Most data work is a chain of steps: pull data, clean it, join it, aggregate it, publish it. A DAG states the order directly: each step runs only once the steps it depends on have finished.

2. **Orchestrators are built around them.** In Apache Airflow, Dagster and Prefect, a pipeline is literally a DAG. Airflow even calls each pipeline a "DAG." The scheduler reads the graph to decide what can run, what has to wait, and what can run in parallel. In the example above, the two extracts run at the same time.

3. **dbt builds one for you.** Each time a model uses `ref('other_model')`, dbt adds an edge. From that graph it works out the build order, and you can run just part of it, like "this model and everything downstream" (`dbt build -s my_model+`).

4. **Failures and reruns are easier to handle.** If `join_orders_customers` fails, the orchestrator knows to skip `build_revenue_report` and leave the extracts alone. Once you fix it, you rerun from the failed node instead of starting over.

5. **Lineage and impact analysis.** The same graph answers "if I change this table, what breaks downstream?" and "where does this number come from?"

6. **No loops means it always finishes.** Since there are no cycles, there's always a valid order to run the tasks in (a "topological sort"). A cycle would mean a pipeline that can never complete, so tools reject them outright.

In short, it's the data world's version of a dependency graph, like what `make` or a package manager uses. It comes up constantly because nearly every data tool uses one to decide what runs, in what order, and what's affected when something changes.