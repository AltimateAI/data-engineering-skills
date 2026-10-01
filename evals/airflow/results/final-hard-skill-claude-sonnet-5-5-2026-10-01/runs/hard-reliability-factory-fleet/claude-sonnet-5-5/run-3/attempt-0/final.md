I rewrote `dags/pipeline_factory.py` and added a `warehouse` pool to `pools.json`. A parse of all 140 configs now takes about 0.25 s here and builds the same 140 DAGs every time. I didn't touch the registry or any pipeline config.

- **Parse time:** the 550 KB registry is now read once per parse with the libyaml loader, not once per DAG, and tables are looked up in a dict. A parse of all 140 configs took about 0.25 s, with Airflow already imported. The 28 s was almost entirely the per-DAG registry read.
- **Stable DAGs:**
  - **Start minute:** it now comes from `zlib.crc32(name) % 60` instead of the per-process-salted `hash()`. An explicit `schedule.minute` still wins, and each pipeline's minute depends only on its own name.
  - **Owners:** they are sorted.
  - **`doc_md`:** the timestamp is gone, which was a second source of new versions.
  - **Result:** parses under two different `PYTHONHASHSEED` values gave identical serialized hashes for all 140 DAGs.
- **Broken configs:** each config is validated, built unregistered, and checked for cycles and a valid cron inside its own `try`. A failure logs `Skipping pipeline config <path>: <error>` and only that DAG is missing. I tried a YAML syntax error, an empty file, a blank file, a cycle, a bad cron, a duplicate step, an unknown tier and a duplicate `dag_id`. Each was skipped and named in the output, the file had no import error, and the other 140 DAG hashes were unchanged. A config with no `tier` or an unknown one is now rejected as broken. Every current config has one of the two values.
- **Workers:** the file reads the parsing context's DAG id and builds only `<dag_id>.yaml`. With `billing_carriers` set it built just that DAG, with the same hash as in a full parse. It falls back to scanning every config if no file has that name; all 140 current files match their `name`.
- **Warehouse limit and priority:**
  - **Pool:** every task uses pool `warehouse`, defined with 16 slots in `pools.json`. `airflow pools import pools.json` worked, and I kept `default_pool`.
  - **Priority:** tasks use `weight_rule="absolute"` with `priority_weight` 100 for critical and 1 for standard, so a critical task always beats a standard one however many steps either pipeline has. I read these back from `billing_carriers` and confirmed the standard values, but didn't separately check a critical DAG.
- **Unchanged:** dag_ids, tasks, dependencies, owners, retries and hour/days are as before. Existing DAGs get new minutes because `hash()` became crc32, so the schedule changes once, at deploy.
- **Task run:** `airflow dags test billing_carriers 2026-03-02` ran all three steps successfully.

I didn't measure parse time with the file's own import cost included, which is where prod's slowness will show. I also didn't check that pool slots actually cap concurrency, since there is no scheduler locally.