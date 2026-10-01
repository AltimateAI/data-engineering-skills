I rewrote `dags/pipeline_factory.py` and added the pool to `pools.json`; every requirement on your list is now met and was checked locally. Nothing is committed, and the registry and pipeline configs are untouched.

## What was wrong

- **Import timeout:** the 550 KB `registry.yaml` was re-read for every one of the 140 DAGs using PyYAML's slow pure-Python loader (about 0.5 s each). The full parse took 78 s locally, and workers repeated it before every task.
- **A new DAG version on every parse:** the start minute used `hash(name) % 60`, and Python's `hash()` gives a different value in each process. On top of that, owners came from a `set`, whose order also varies per process, and `doc_md` contained `datetime.now()`.
- **One broken config took out the whole fleet:** nothing caught per-file errors, so one bad YAML file was an import error for the entire factory file.
- **Finance close ran late:** there was no fleet-wide limit and no priority between tiers.

## What changed

- **Parse speed:** the registry is read once per parse with the fast libyaml loader.
- **Stable versions:**
  - The start minute is now `zlib.crc32(name) % 60`, which depends only on the pipeline's own name and is the same in every process.
  - Owners are kept in a fixed order: team owners first, then any extra owners from the config.
  - `doc_md` no longer contains a timestamp.
- **Isolation:** each config is checked as plain data before its DAG is built. A bad file is skipped and an error naming it is logged, so it never leaves a half-built DAG behind. The checks cover:
  - YAML syntax and empty files
  - team, tier, hour, minute and retries
  - unknown tables, duplicate steps and unknown `depends_on`
  - invalid cron days and dependency cycles
- **Workers:** the factory reads Airflow's parsing context, so a worker running a task loads only `<dag_id>.yaml` and builds just that DAG.
- **Warehouse:** a `warehouse` pool with 16 slots is in `pools.json`, and every task uses it.
- **Tier priority:** critical tasks get weight 100 and standard tasks get 1, with `weight_rule="absolute"`. That makes a task's priority its tier's weight, however many steps its pipeline has. Under the default rule, weights add up over downstream tasks, so long standard pipelines outranked short critical ones.

**New rule for config owners:** a config's `name` must match its file name. All 140 configs already do. Without this rule, a copied config that kept the old `name` would claim and replace another team's DAG, and workers couldn't map a dag_id to its file without parsing everything. You may want to tell the platform team.

## Test results (Airflow 3.3.2)

- **Parse time:** 0.25 s for all 140 DAGs, with no import errors; the skill's DAG checker passes. With the parsing context set to one dag_id, the parse builds only that DAG (0.16 s), and it is identical to the full-parse version.
- **Same DAGs as today:** compared with the original factory, all 140 have the same dag_ids, tasks, dependencies, owners, retries, hour and days.
  - Explicit `schedule.minute` values are kept.
  - The 114 pipelines without one are spread over 57 different minutes, at most 5 per minute and 2 at :00.
  - The original was nondeterministic, so those 114 now have new fixed minutes rather than their old ones.
- **Stable hashes:** two parses under different Python hash seeds produced identical DAG hashes.
- **Isolation:** I added 10 deliberately broken copies (bad YAML, empty file, cycle, hour 25, invalid days, duplicate step, unknown upstream, unknown table, unknown tier, and a copy reusing another pipeline's name) plus one valid copy.
  - Each broken file was skipped, with its file name in the error log, and there was no import error.
  - None of the 140 existing DAGs changed; only the valid copy appeared.
  - Removing `billing_attribution` changed no other DAG.
  - I deleted the test copies afterwards.
- **Pool and priority:** `airflow pools import pools.json` created `warehouse` with 16 slots, and every task is in that pool with the expected weight.
- **Real runs:** `airflow dags test` of `billing_chargebacks` (critical) and `billing_carriers` (standard) both succeeded, with each step running once in dependency order.

**Not tested:** with no scheduler running locally, I couldn't watch the 16-slot cap or the critical-first ordering under real load; these come from standard pool and priority settings. Priority only decides which queued task gets the next free slot. A running standard query keeps its slot until it finishes.