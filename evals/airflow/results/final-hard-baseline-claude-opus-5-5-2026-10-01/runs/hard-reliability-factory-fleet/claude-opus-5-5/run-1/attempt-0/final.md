The factory is fixed and meets each of your requirements. I checked them with the airflow CLI and test scripts run against copies of the project; your configs and `configs/registry.yaml` are untouched. Nothing is committed yet. I changed `dags/pipeline_factory.py` and `pools.json`, and documented the new behaviour in `README.md`.

**What was wrong**
- **Slow parse:** the 553 KB registry was re-read for every one of the 140 configs with the slow pure-Python YAML loader. That took ~74 s locally.
- **New version on every parse:** three things changed between parses: the start minute (`hash(name) % 60`, and Python's `hash()` differs per process), the owner order (built from a set), and `datetime.now()` inside `doc_md`.
- **One broken config hid everything:** the build loop had no error handling, so one exception failed the whole file.

**What changed**
- **Parse time:** the registry is read once per parse, with the fast C YAML loader. A full parse now takes ~1.7 s, Airflow import included.
- **Stable DAGs:** the start minute comes from a stable checksum of the pipeline name, owners keep their order with duplicates removed, and the timestamp is gone from `doc_md`. An explicit `schedule.minute` still wins. Auto-picked minutes land on 57 different minutes of the hour.
- **Broken configs:** each config is checked before its DAG is built: YAML errors, unknown team or table, a missing or invalid tier, unknown or circular `depends_on`, duplicate steps, and a bad hour, minute or days. A config that fails is skipped and logged as `Skipping pipeline config <path>: <error>`. Airflow itself only checks the cron string later, so I check it with croniter when the DAG is built.
- **Worker parses:** a worker running a task reads only the registry and that task's own config, and builds only that DAG.
- **Warehouse limit:** `pools.json` now defines a `warehouse` pool with 16 slots, and every task runs in it.
- **Critical first:** critical pipelines get priority 100 and standard ones get 1, with Airflow's `absolute` weight rule. Normally Airflow adds up a task's downstream weights, so a pipeline with more steps gets more priority; with `absolute` the step count doesn't matter.

**Decision for you:** a config's `name` must now equal its file name. That keeps two configs from fighting over one dag_id and lets a worker find its config without reading the rest. All 140 configs already follow it. A new config that copies an existing name is rejected and only it disappears, but the platform team should know about the rule.

**How I checked it**
- **Same as before:** compared with the original factory, all 140 DAGs have identical dag_ids, tasks, dependencies, owners, retries, hours, days and explicit minutes.
- **Stable:** two runs with different Python hash seeds gave identical serialized DAGs for all 140.
- **Isolation:** on a copy of the project, I broke four configs (a YAML syntax error like the `billing_reconcile` one, an unknown table, a dependency cycle, a duplicate name). Only those DAGs disappeared, each with an error naming its file. Adding a new valid config changed no other DAG.
- **CLI:** `airflow dags list-import-errors` reports none, `airflow pools import pools.json` works, and `airflow dags test finance_inventory 2026-03-02` ran every step successfully on a project copy.

I couldn't check the pool limit or the critical-first ordering in action, because that needs a running scheduler. I've only confirmed the pool and priority settings on every task.