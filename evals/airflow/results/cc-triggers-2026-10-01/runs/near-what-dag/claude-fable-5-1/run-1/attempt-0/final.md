A DAG is a directed acyclic graph. It is a set of nodes connected by arrows, where the arrows have a direction and you can never follow them in a loop back to where you started.

Data engineers lean on the idea because a pipeline is naturally a DAG:

- **Nodes are steps.** Extract from an API, load raw data, clean it, join it, build a report table.
- **Arrows are dependencies.** "Clean" depends on "load raw", so the arrow points from load to clean. A step can only run once everything pointing into it has finished.
- **No cycles** means the whole thing can actually complete. If A needed B and B needed A, nothing could ever start. Acyclic guarantees there is always a valid run order, found by a topological sort.

That structure buys a few practical things:

- **Scheduling and parallelism.** Independent branches can run at the same time, and the orchestrator knows exactly what has to wait.
- **Lineage.** You can trace any output table back through its upstream sources, and see what breaks downstream if you change something.
- **Partial reruns.** If one step fails, you rerun it and only its descendants, not the whole pipeline.

The word is everywhere because the main tools are built around it. In Apache Airflow, the Python file defining a pipeline is literally called a DAG. dbt builds a DAG from the `ref()` calls between models and uses it to decide build order. Dagster, Prefect, Spark's execution planner, and even Git's commit history are all DAGs under the hood.