I rewrote the factory in `dags/pipeline_factory.py` and added the `warehouse` pool to `pools.json`. I did not edit the registry or any pipeline config.

**What I checked**
- **Parse time:** all 140 DAGs load in about 0.3 s on this laptop, with no import errors.
- **Same DAGs every parse:** serialized hashes are identical across two different `PYTHONHASHSEED` values.
- **Broken configs:** I added five broken configs: empty file, YAML syntax error, dependency cycle, invalid cron hour, duplicate step. Each was skipped, and each log line names its config file. The 140 real DAGs kept identical hashes and the DagBag had no import errors.
- **Worker parse:** with `_AIRFLOW_PARSING_CONTEXT_DAG_ID=billing_carriers`, only `billing_carriers` is built.
- **Pool and priority:** `airflow pools import pools.json` created `warehouse` with 16 slots. A critical DAG's tasks showed `warehouse` / `absolute` / 100 and a standard DAG's showed `warehouse` / `absolute` / 1.
- **Run:** `airflow dags test billing_carriers 2026-03-02` succeeded.
- **Cleanup:** I deleted the scratch files and the `output/` directory the test run created.

**Not verified:** nothing ran against a real scheduler or warehouse, and I did not time a slow production box. I did not test adding or removing a real config beyond the broken-file cases.

**What changed**
- **Parse time:** the 550 KB registry was being re-read once per DAG. It is now parsed once per process with the faster libyaml loader, and tables are looked up in a set.
- **Stable DAGs:**
  - The start minute came from `hash()`, which changes per process, so I replaced it with `crc32(name) % 60`. An explicit `schedule.minute` still wins.
  - Owners were joined in set order, so they are now sorted.
  - The "generated on <now>" timestamp is gone from `doc_md`.
  - Every DAG's start minute (minutes were random per parse before) and the order of its owners may differ from what is in the UI now, so expect one new version per DAG on the first deploy.
- **Isolated failures:**
  - Each config is checked as data first: required keys, tier, team, known tables, unique steps, known dependencies, valid cron, and no cycles.
  - It is then built without registering, and any error is logged as `Skipping pipeline config <path>` with the reason.
  - The DAG is registered only if everything passed, so a broken pipeline is absent and the rest load.
- **Worker parse:** when a parsing context names a DAG, the factory builds only that one, using `<dag_id>.yaml`. Every current config's filename matches its `name`. I made a mismatch a config error, since the lookup depends on it.
- **Priority:** every task uses pool `warehouse` with the `absolute` weight rule, 100 for critical and 1 for standard. Step count no longer affects priority.

**Review:** the new rule that `name` must match the filename is stricter than before, so a config that renames itself will now drop out of the fleet.