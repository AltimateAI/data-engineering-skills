I rewrote `dags/pipeline_factory.py` and added the `warehouse` pool to `pools.json`; all your requirements now hold and I tested each one locally. The file now parses in **1.7 s** instead of 73 s. It produces exactly the same DAGs on every parse, and a broken config only takes out its own DAG. Nothing is committed yet.

**What was wrong**
- **Slow parse:** the 553 KB `registry.yaml` was re-parsed with the slow pure-Python YAML loader once per config, 140 times. It's now parsed once with the C loader (0.07 s).
- **New DAG version on every parse:** three things changed from one parse to the next.
  - The start minute used `hash(name) % 60`, and Python's `hash()` changes from process to process.
  - The owner string was built from an unordered set.
  - `doc_md` included `datetime.now()`.

  Minutes now come from a stable checksum of the pipeline's own name. Owners are listed team first, then config extras, without duplicates. The timestamp is gone.
- **One bad config killed the fleet:** any error stopped the whole file. Each config is now checked and built on its own. A bad one is skipped and logged as `Skipping pipeline config configs/pipelines/<file>.yaml ...: <reason>`. The checks cover YAML syntax, missing fields, unknown team or table, tier, hour/minute/days, retries, duplicate or unknown steps, and dependency cycles.
- **Workers built all 140 DAGs:** the file now uses Airflow's parsing context, so a worker running a task builds only that task's DAG.
- **Critical pipelines starved:** every task now runs in pool `warehouse` (16 slots). Critical tasks get a priority of 100 and standard tasks 1, with a weight rule that doesn't add up a pipeline's steps. So any critical task is picked before any standard one, however many steps either has.

**How I tested it**
- **Nothing lost:** compared with the old factory, all 140 pipelines have identical dag_ids, tasks, dependencies, owners, retries, hours, days and descriptions. All 26 explicit `schedule.minute` values are kept, and the other start minutes are spread over the hour.
- **Same output every parse:** the saved DAG fingerprints were identical in runs with different hash seeds. After `airflow dags reserialize` three more times, the database still had exactly 140 DAG versions.
- **Isolation:** I used a scratch copy of the project so the real configs weren't touched. I added a `billing_reconcile` with a YAML syntax error, then with a cycle, an unknown table, an unknown team, an unknown step and a wrong name. Each time it was the only DAG missing, the log named its file, and no other DAG's fingerprint changed. Adding a valid config or removing one also left every other DAG unchanged.
- **Worker parse:** builds exactly 1 DAG, identical to the full parse.
- **CLI:** `airflow pools import pools.json` loads `warehouse` with 16 slots, and `airflow dags test billing_carriers 2026-03-02` succeeds with its tasks running in the `warehouse` pool. To run the CLI locally I had to run `airflow db migrate` on the local SQLite database first.

**Decisions for you**
- **New rule: a config's `name` must match its file name** (`foo.yaml` → `name: foo`). All 140 configs already follow it. This is what makes the worker path exact, and it means a new file can never clash with an existing dag_id. If the platform team needs names that differ from file names, this has to change.
- **Start minutes change once:** pipelines without an explicit minute get a new fixed minute. The old ones were different on every parse anyway, so expect one last new version per DAG when this deploys.
- **Import the pool before the new DAGs go live.** Tasks assigned to a pool that doesn't exist won't be scheduled.
- **The registry is still a single point of failure:** if `registry.yaml` itself is unreadable, the error is logged and no fleet DAGs load, since every pipeline depends on it.