I rewrote `dags/pipeline_factory.py` and added the `warehouse` pool to `pools.json`, so the fleet should now parse quickly, build the same DAGs every time and survive a broken config. I checked parse time, determinism, a broken config and the worker path locally. I did not run `airflow pools import` or test a real warehouse saturation. The DB isn't migrated here, so I ran the module directly instead.

Results from my local runs:

- **Parse time:** about 1.7 s for all 140 configs, against your 5 s target. The registry is now read once instead of once per config, and YAML uses the C loader.
- **Same DAGs every parse:** two runs with different `PYTHONHASHSEED` gave byte-identical output. Several things were changing between parses before:
  - the start minute came from `hash()`, which varies per process, so it is now a CRC32 of the name;
  - the owner list came from a `set`, so owners are now ordered, team first and then the config's extras, without duplicates;
  - `doc_md` carried `datetime.now()`, which I removed;
  - config files are now read in sorted order.
- **Broken config:** I corrupted `billing_spend.yaml` temporarily and 139 DAGs still loaded. The error log names the file (`.../billing_spend.yaml`, line 2, column 6) and that DAG is absent. The factory now also rejects:
  - a missing or unknown team;
  - an unknown tier;
  - an out-of-range hour or minute;
  - empty or duplicate steps;
  - an unknown table;
  - a `depends_on` pointing at a step that doesn't exist;
  - dependency cycles;
  - a `name` that differs from the file name.

  A bad registry logs an error and builds no fleet DAGs.
- **Workers:** the factory reads Airflow's parsing context for the DAG id. Setting it to `billing_carriers` built only that DAG, and an id with no config builds nothing.
- **Warehouse limit and priority:**
  - Every task now uses the `warehouse` pool with one slot, and `pools.json` defines that pool at 16 slots.
  - Critical tasks get priority 1000 and standard tasks get 1, with the absolute weight rule. Step count no longer affects priority, since the default rule sums downstream weights.
  - Priority only decides order once the pool is full, which is the case you described.
- **What stays the same:** dag_ids, tasks, dependencies, retries, hour and days are unchanged. An explicit `schedule.minute` still wins.

An existing deployment's DAG versions will change once on the first parse after this lands, because the minute, owner order and docs text differ.

I did not touch `configs/registry.yaml` or any pipeline config.