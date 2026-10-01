A DAG is a Directed Acyclic Graph. It is a set of nodes connected by arrows, where the arrows have a direction and you can never follow them in a loop back to where you started.

Why data engineers care:

- **A pipeline is naturally a DAG.** Each node is a step, such as "extract orders" or "build the revenue table". Each arrow means "this step needs that step's output first". The acyclic rule is just common sense: a step can't depend on something that depends on it.
- **It gives you an execution order for free.** Topological sort turns the graph into a valid run sequence, and anything not connected by an arrow can run in parallel. The scheduler figures that out instead of you hand-writing step 1, step 2, step 3.
- **It makes failures and reruns tractable.** If one step fails, you know exactly which downstream steps are blocked and which upstream ones are still fine. You rerun only the affected subgraph.
- **It gives you lineage.** Walking the arrows backwards tells you where a table's data came from. Walking forwards tells you what breaks if you change it.

Two tools make the word unavoidable. In Apache Airflow, a DAG is literally the unit of deployment: a Python file defines one and its tasks, and the scheduler runs it. In dbt, every `ref()` between models builds the DAG implicitly, and commands like `dbt build --select my_model+` select nodes by walking it.

So when someone says "add it to the DAG" or "the DAG is broken", they mean the dependency graph of pipeline steps and the tool that executes it, not anything exotic from graph theory.