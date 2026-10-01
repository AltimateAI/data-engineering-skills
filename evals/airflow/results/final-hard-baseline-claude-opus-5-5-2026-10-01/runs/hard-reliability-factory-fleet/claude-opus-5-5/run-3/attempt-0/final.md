I fixed the factory and checked each of your requirements locally. The changes are in `dags/pipeline_factory.py` and `pools.json`, plus a short note in `README.md`. Nothing is committed yet.

**What was wrong**
- **Slow parse:** the 553 KB `registry.yaml` was re-read for each of the 140 configs using PyYAML's slow pure-Python loader. A full parse took **73 s** on my laptop.
- **New DAG versions on every parse:** three things changed between parses even when no config did:
  - The start minute came from Python's `hash(name)`, which gives a different result in every process.
  - `doc_md` included the current time.
  - Owners were joined from a `set`, so their order changed from process to process.
- **One bad config took out every DAG:** nothing caught an error in a single config, so it failed the whole file.
- **Warehouse overload and late critical runs:** there was no pool, and Airflow ranks a task by how many steps come after it. Long standard pipelines therefore outranked short critical ones.

**What I changed**
- **Speed:** the registry is now loaded once, with PyYAML's fast C loader. A full parse takes about **1.5 s**, most of which is importing Airflow.
- **Same DAGs every parse:**
  - Start minutes now come from a fixed checksum of the pipeline name (`crc32`), so they stay the same across parses. They're spread over 57 different minutes, and an explicit `schedule.minute` still wins.
  - The timestamp is gone from `doc_md`.
  - Owners are listed team owners first, then any the config adds, without duplicates.
  - Nothing in a DAG depends on any other config.
- **Broken configs:** each config is fully checked before its DAG is built. That covers YAML syntax, team, tier, hour and minute ranges, unknown tables, duplicate or unknown steps, dependency cycles and the cron expression. A bad config is skipped and logged as `Skipping pipeline config <path>: <reason>`. Partly built DAGs are never published.
- **Workers:** when a worker parses the file to run a task, it reads only that pipeline's config and builds one DAG, in about 0.17 s.
- **Warehouse limit:** every task now runs in the `warehouse` pool. `pools.json` defines it with 16 slots, alongside the existing `default_pool`.
- **Critical first:** critical tasks get a fixed priority of 100 and standard tasks get 1, whatever the number of steps.

**How I checked it**
- **Determinism:** three separate parses produced byte-identical serialized DAGs, all 140 of them.
- **Nothing lost:** compared with the original factory, the dag_ids, tasks, dependencies, owners (as a set), retries, hours and days all match, with no differences.
- **Isolation:** I added a broken `billing_reconcile.yaml` like Tuesday's and temporarily broke `billing_orders`. Only those two DAGs disappeared, the other 139 came out byte-identical, and the log named the file. I then removed the test file and restored `billing_orders`.
- **CLI:** `airflow pools import pools.json` creates `warehouse` with 16 slots, and `airflow dags test billing_carriers 2026-03-02` succeeds.
- **Not tested:** the actual queuing order. There's no scheduler locally, so I confirmed only that the pool and priorities come through to the serialized DAGs correctly.

**Decisions for you to confirm**
- **Owner order:** the old owner string had a random order, so it will change once to the new stable order. This counts as one more DAG version per pipeline when you deploy; after that, versions only change when a config does.
- **Duplicate pipeline names:** if two configs use the same `name`, the file named after the pipeline keeps it and the other is skipped with an error. If neither file matches, both are skipped. This stops a copied config with a forgotten rename from taking over an existing DAG.
- **Missing `tier`:** a config without a `tier` is treated as `standard`; an unknown value counts as a broken config. All 140 current configs set it.