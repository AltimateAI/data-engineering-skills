I rewrote `dags/pipeline_factory.py` and added the `warehouse` pool (16 slots) to `pools.json`. Parsing, determinism, a broken config and the single-DAG build all checked out in a local DagBag. I didn't run the dag-processor, a scheduler, a real warehouse, or the skill's `airflow_check.py`/`replay_runs.py` scripts.

**What changed**
- **Parse time:** the full fleet (140 DAGs) parsed in about 0.2 s on my machine, well under the 5 s target. The 20k-line `registry.yaml` is now loaded once per parse with the C YAML loader. Only team data and table names are kept.
- **Same DAGs every parse:**
  - The start minute now comes from `crc32(name) % 60`. It was `hash()`, which is salted per process and was the cause of the new DAG versions. An explicit `schedule.minute`, including `0`, still wins.
  - Owners are sorted, and the parse-time timestamp is gone from `doc_md`.
  - Parsing under two different `PYTHONHASHSEED` values gave identical DAG hashes for all 140 DAGs.
- **Broken config isolation:**
  - Each config is validated as data, built without auto-registering, and checked for cycles before it is accepted. The checks are required keys, tier, team, cron, duplicate steps, unknown tables and unknown dependencies.
  - A bad config is logged as `Skipping pipeline config <full path>: <error>` and that DAG is absent. A deliberately malformed copy of a config gave exactly that log line. The other 140 DAGs still loaded and the file had no import error.
  - I couldn't compare the other DAGs' hashes against the baseline in that run, because my hash-comparison script broke on log lines mixed into its output.
  - I didn't test the other failure modes: a dependency cycle, bad cron, unknown table or unknown dependency. I never built a real cycle, because my test copy of a config wasn't actually broken.
- **Worker parse:** with `_AIRFLOW_PARSING_CONTEXT_DAG_ID` set, only `configs/pipelines/<dag_id>.yaml` is read and built. I tried `billing_orders` and got exactly one DAG in about 1.7 s, most of it the registry load. If no file matches the dag_id, it falls back to scanning all configs.
- **Warehouse limit and priority:** every task uses `pool="warehouse"` with `weight_rule="absolute"`. Critical tasks get weight 100 and standard tasks get weight 1, so step count no longer matters. The DagBag shows 98 critical tasks at 100 and 584 standard tasks at 1.
- **Unchanged:** dag_ids, tasks, dependencies, owners, retries, hour and days. I didn't edit `registry.yaml` or any pipeline config.

`airflow pools import pools.json` uploaded both pools in a throwaway Airflow home. `airflow dags test billing_orders 2026-03-02` succeeded.

The minute assignments are new: any config without an explicit `schedule.minute` now gets a different minute than it did under the old `hash()`. That was effectively random per parse anyway.

I cleaned up the test configs and the `output/` directory the test run created.