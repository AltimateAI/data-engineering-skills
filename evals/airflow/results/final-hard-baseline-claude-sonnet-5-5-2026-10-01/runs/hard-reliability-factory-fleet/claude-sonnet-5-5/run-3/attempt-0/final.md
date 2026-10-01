I fixed the factory in `dags/pipeline_factory.py` and added the pool to `pools.json`. It now loads all 140 DAGs in about 0.2s of DagBag time (1.7s wall for the bare script). I checked this with a local DagBag parse, since there's no scheduler. I did not run `airflow pools import`, and I did not simulate warehouse contention, so the 16-slot cap and the critical-first ordering are untested end to end. I haven't committed anything.

**Parse speed.** The old code re-read the 20k-line registry once per config, using the slow pure-Python YAML loader. The registry now loads once, and both it and the configs use libyaml's C loader.

**Same DAGs on every parse.** Three things varied from parse to parse:
- The start minute used Python's `hash()`, which changes per process. It's now `crc32(name) % 60`, so it's stable and still spread over the hour. An explicit `schedule.minute` still wins.
- `doc_md` contained `datetime.now()`. I removed the timestamp.
- The owners string came from an unordered set. It's now sorted, and config files are read in sorted order.

Two separate processes produced byte-identical serialized DAGs. The minutes will differ from whatever the random hash gave before, so each DAG gets one new version on deploy.

**Broken configs.** Each config is built inside its own try/except. A failure logs an error naming the config file and skips only that DAG. With a deliberately broken `billing_carriers.yaml`, 139 DAGs loaded and the error line named the file. This also covers an unknown table, an unknown tier, and a duplicate `dag_id` (the later file is skipped).

**Worker parsing.** The factory reads `get_parsing_context().dag_id` and builds only the config whose filename matches it. All 140 filenames match their `name`, which I checked. With the context set to `billing_carriers`, exactly one DAG loaded. If no file matches the requested id, it falls back to loading everything.

**Warehouse limit and priority.**
- Every task uses the new `warehouse` pool with 16 slots, defined in `pools.json`.
- Priority weights are absolute: 1000 for critical and 1 for standard. The default rule adds up downstream weights, which is how a standard pipeline with many steps could outrank a critical one. Under the new rule, critical tasks are always picked first however many steps either pipeline has.

I didn't touch the registry or the pipeline configs.