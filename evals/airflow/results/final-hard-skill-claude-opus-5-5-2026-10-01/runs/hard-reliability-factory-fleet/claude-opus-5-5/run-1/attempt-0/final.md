I rewrote the factory and added the `warehouse` pool to `pools.json`. Every requirement checked out locally on Airflow 3.3.2. I didn't touch the registry or any pipeline config.

**What was causing the problems**
- **Slow parse:** the 553 KB `registry.yaml` was re-read with the slow pure-Python YAML loader once for each of the 140 DAGs.
- **New version on every parse:** the start minute came from `hash(name)`, which Python randomises per process. `doc_md` also included `datetime.now()`, and the owner list was built from a `set`, whose order also changes from run to run.
- **Whole fleet disappearing:** nothing caught a bad config, so one error failed the import of the whole file and took every DAG with it.

**What changed**
- **Speed:** the registry is now read once per parse with the fast YAML loader. Parsing all 140 DAGs takes about 0.22 s; a worker parse is about 0.15 s.
- **Stable DAGs:** the start minute comes from a CRC32 of the pipeline name, so it's stable but still spread out: 57 different minutes, and only 2 pipelines without an explicit minute land on :00. An explicit `schedule.minute` still wins. The clock is gone from `doc_md`, and owners are listed as team owners first, then the extras from the config, without duplicates. Each DAG depends only on its own config and the registry.
- **Broken configs:** each config is read and checked inside its own error handler before any DAG object is created. The checks cover YAML syntax, required and unknown keys, team, tier, hour, minute and days, registered tables, duplicate steps, unknown dependencies and cycles. A bad config is skipped, and an error naming the file goes to the log and the parse warnings. DAGs are built so that a half-finished one can't be left behind and picked up.
- **Workers:** when a worker parses the file for one task, it loads only `configs/pipelines/<dag_id>.yaml`.
- **Warehouse limit and priority:** every task runs in the `warehouse` pool (16 slots, now in `pools.json`). Critical tasks have priority 100 and standard tasks priority 1, with `weight_rule="absolute"` so the number of steps in a pipeline doesn't change the ranking.

**Two things that behave differently**
- **File name must match `name`:** a config's `name` must now match its file name. All 140 do today. This is what makes the worker lookup work, and it means two configs can't claim the same dag_id.
- **One-time version change:** on this deploy every DAG gets one new version, because its start minute is now stable (and so changes once) and `pool`/`priority` are new. After that, versions only change when a config changes.

**Verified locally**
- The DAG checker passes with no import errors. Its only warning is about the cron timetable, which is the same schedule type as before.
- Parsing in two processes with different hash seeds gives identical hashes for all 140 DAGs.
- Compared with the original factory, all 140 DAGs have the same dag_ids, tasks, dependencies, owners, retries, retry_delay, hour, days, explicit minutes, descriptions and tags.
- I added 12 broken configs: bad YAML (the `billing_reconcile` error), an empty file, an unknown key, an unknown upstream step, a cycle, hour 25, invalid days, a duplicate step, an unknown table, team or tier, and a name that doesn't match its file. Each was rejected with one error line naming its file. There was no import error and the other 140 hashes didn't change. A valid new config and a removed config also left the others unchanged. I deleted the test files afterwards.
- With the worker parsing context set, only that one DAG was built, and its hash matched the full parse.
- `airflow pools import pools.json` uploaded both pools.
- `airflow dags test` of `billing_chargebacks` (critical) and `billing_carriers` (standard) succeeded, with each step running once in dependency order.

**Not verified:** with no scheduler running locally, I couldn't watch the pool hold at 16 slots or see critical tasks being picked first under load. That rests on the pool and priority settings, which I confirmed are on every task. The parse-time error log was checked through the DagBag, not a real dag-processor.