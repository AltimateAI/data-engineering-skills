I rewrote `dags/pipeline_factory.py` and added the `warehouse` pool to `pools.json`. I couldn't run `airflow dags test`, because the local Airflow DB needs `airflow db migrate` first. I haven't checked task execution, the pool, or the priorities in a running Airflow.

I checked parsing by importing the file directly:
- All 140 DAGs build in about 1.6 s.
- Setting the worker's parsing context to `billing_carriers` builds exactly one DAG.
- A deliberately broken config added to `configs/pipelines/` was skipped and logged with its full path. The other 140 still loaded. I deleted that test file afterwards.

- **Parse time:** the 20k-line registry is now parsed once, with the C YAML loader, instead of once per config.
- **Same DAGs every parse:**
  - The start minute now comes from `zlib.crc32(name) % 60` instead of `hash()`, which changes on every Python process.
  - The timestamp is gone from `doc_md`.
  - Owners keep a stable order: team owners first, then the config's extras. Before, they came from a set, so the order varied.
  - Start minutes are still spread over the hour, and an explicit `schedule.minute` still wins. The specific minutes differ from before, since the old values were random per process.
- **Broken configs:** each config is built and checked on its own, and a failure is logged as `Skipping pipeline config <path>: …`. Only that DAG is dropped. The checks cover:
  - unknown table, team or tier;
  - bad hour or minute;
  - empty steps;
  - dependencies on unknown steps;
  - dependency cycles;
  - a `dag_id` that another config already uses (the first file alphabetically keeps it).
- **Workers:** the factory reads the DAG id Airflow gives it during task startup and builds only that config, found by matching the file name. If no file name matches, it falls back to a light text scan for `name:`.
- **Warehouse limit:** every task now runs in the `warehouse` pool, which has 16 slots in `pools.json`. `default_pool` is unchanged.
- **Critical before standard:** critical tasks get priority weight 1000 and standard tasks get 1. The weights are absolute rather than the default sum over downstream tasks. A critical pipeline therefore always outranks a standard one, however many steps either has.

The deploy still needs `airflow pools import pools.json`. I left the registry and the pipeline configs untouched.