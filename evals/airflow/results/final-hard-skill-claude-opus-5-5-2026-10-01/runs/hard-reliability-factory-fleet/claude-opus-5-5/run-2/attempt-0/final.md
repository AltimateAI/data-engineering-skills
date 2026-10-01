The factory is fixed. A full parse of all 140 pipelines now takes about 0.2 s (it timed out at 30 s before), and I checked every requirement you listed on Airflow 3.3.2. I changed `dags/pipeline_factory.py` and `pools.json`, added a few lines to `README.md`, and didn't touch the registry or any pipeline config. Nothing is committed yet.

**What was wrong:**
- **Slow parse:** the factory re-read the 550 KB `registry.yaml` once per pipeline (140 times) with the slow pure-Python YAML loader. It now reads it once per parse with the fast C loader.
- **New versions on every parse:** three things changed between parses. The start minute came from `hash(name)`, which differs in every process. Owners came out of a `set` in random order. The DAG docs contained `datetime.now()`. The minute is now `zlib.crc32(name) % 60`, which depends only on the pipeline's own name. Owners are listed as team owners then config extras, without duplicates, and the timestamp is gone.
- **One bad config took out every DAG:** each config is now read, checked and built separately. A bad one is skipped and logs `Skipping pipeline config <file>.yaml: <reason>` (also recorded as a parse warning). The checks cover bad or empty YAML, unknown team, tier, table or step, duplicate steps, cycles, invalid schedule and invalid step names. Its DAG is not registered at all, not even half-built.
- **Workers built all 140 DAGs:** when a worker parses the file to run a task, it now loads only `configs/pipelines/<dag_id>.yaml`.
- **Warehouse limit and priority:**
  - `pools.json` adds a `warehouse` pool with 16 slots.
  - Every task runs in that pool with `weight_rule="absolute"`, priority 100 for critical and 1 for standard.
  - The weight no longer grows with the number of downstream steps, so a critical task always outranks a standard one.

**What I checked:**
- **Speed and stability:** a full parse took 0.22–0.24 s with 140 DAGs and no errors. Importing the file in a fresh Python process, Airflow included, took 1.7 s. Every DAG's version hash was identical across two parses with different hash seeds.
- **Nothing lost:** I compared against the original factory's output. All 140 have the same dag_ids, tasks, dependencies, owners, retries, hour, days, tags and descriptions. Every explicit `schedule.minute` is kept, and the rest are spread over 57 different minutes.
- **Broken configs:** in a copy of the project I added 12 broken configs (one per failure type), added one good config and removed one existing one.
  - Each broken config was skipped, with an error naming its file.
  - The file had no import error, and no other DAG's hash changed.
- **Worker parse:** with a task's DAG id set, as a worker sets it, only `finance_ledger` was built, and its hash matched the full parse.
- **Runs:** the skill's DAG checker passed; its only warnings note that `{{ ds }}` is the day each run fires, the same schedule behaviour as before. `airflow pools import pools.json` loaded both pools. `airflow dags test` succeeded for `billing_chargebacks` (critical) and `billing_orders` (standard), with each step running once in dependency order.

**Before you deploy:**
- **One new rule:** a config's `name` must match its file name. All 140 do today. This keeps dag_ids unique, so a new config can't silently replace an existing DAG, and it's how a worker finds the right config file. It's documented in the README.
- **One-time new versions:** the first deploy creates one new version for every fleet DAG, because of the pool and priority settings, the stable minutes, the owner order and the docs text. After that, versions only change when a config changes.
- **Some start times move once:** pipelines without an explicit minute get a new fixed minute. Before, their minute changed on every parse anyway.

**Not checked:** there's no scheduler locally, so I haven't seen the pool cap or the priority ordering act on real queued tasks. That relies on standard scheduler behaviour, and I only confirmed the settings on every task. Parse time was measured on this laptop, not on prod hardware.