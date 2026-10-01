A DAG is a **Directed Acyclic Graph**. Take the three words one at a time:

- **Graph**: a set of nodes connected by edges. Here the nodes are tasks, like "extract orders" or "build the revenue table".
- **Directed**: each edge points one way. An edge from A to B means "A must finish before B starts", so it expresses a dependency.
- **Acyclic**: there are no loops. You can never follow the arrows and arrive back where you started.

The acyclic part is what makes DAGs useful. Because there are no cycles, there is always at least one valid order to run the tasks in. A scheduler can sort the graph topologically, run things with no unfinished dependencies, and start downstream tasks as soon as everything they depend on is done. A cycle would make that impossible, since A would wait on B while B waits on A.

Data engineers talk about DAGs constantly for a few reasons:

- **Pipelines are naturally DAGs.** Extract raw data, clean it, join it, aggregate it, publish it. Each step depends on earlier ones and never on later ones.
- **Orchestrators are built around them.** In Apache Airflow, the DAG is literally the unit you write and schedule. A Python file defines the tasks and their dependencies, and Airflow runs them in a valid order, retries failures, and shows the graph in the UI. Dagster, Prefect, and others use the same concept under different names.
- **dbt builds one automatically.** Every `ref()` call between models is an edge. dbt infers the whole graph, runs models in dependency order, and parallelizes branches that do not depend on each other.
- **They enable the things people care about.** Lineage is just walking the graph upstream. Impact analysis is walking it downstream. Backfills, partial reruns, and parallelism all fall out of knowing the dependency structure.

So when someone says "add it to the DAG" or "the DAG broke", they usually mean the pipeline definition and its dependencies, not graph theory in the abstract.