The work is complete. Here is the report.

**Airflow version:** 3.3.2 (requirements.txt pin matches the installed env).

**Changed files**
- `dags/pipeline_factory.py`: rewritten. Registry is parsed once per import with the libyaml loader instead of once per pipeline (140 parses of a 20k-line file was the whole timeout). Start minutes come from `zlib.crc32(name)` instead of the per-process `hash()`, owners are sorted, and the `datetime.now()` stamp is gone from the doc, so every parse serialises identically. Each config is validated as plain data, then built as an unregistered DAG inside its own try, with `dag.validate()` and `dag.check_cycle()` run before registration. A failure is logged as an error naming the config path and that pipeline is skipped. When a worker sets the parsing context, only that dag_id's config file is read and built. Every task gets `pool="warehouse"`, `weight_rule="absolute"` and priority 100 for critical or 1 for standard via default_args.
- `pools.json`: added the `warehouse` pool with 16 slots and a description (required for import).
- `README.md`: documented the pool, tier priority, and the skip-on-error behaviour.

No pipeline config or registry was touched. The scratch files used for verification live outside the repo.

**Verified in this session**
- Parse time: the old file timed out at 30 s on this laptop. The new file parses all 140 DAGs in about 0.25 s, with no import errors; the skill's checker exits 0.
- Stability: identical hashes for all 140 DAGs across two different `PYTHONHASHSEED` values.
- Preservation: compared old vs new DagBag for every DAG. Same dag_ids, tasks, dependencies, owner sets, retries, hours and days. All 26 explicit minutes kept. Derived minutes use 57 distinct values; only 2 derived pipelines land on :00.
- Isolation: 13 broken configs at once (bad YAML, empty file, scalar, missing key, unknown team/tier/table/upstream, cycle, hour 25, bad day field, duplicate step, and the reconcile-style YAML error). All 140 original hashes unchanged, no import error, every broken pipeline absent, and each file named in a "Skipping pipeline config" error line.
- Add one config and remove another: the other 139 hashes unchanged.
- Worker path: with `_AIRFLOW_PARSING_CONTEXT_DAG_ID=finance_ledger`, exactly one DAG is built, only that config plus the registry are opened, and its hash equals the full-fleet build. An unknown dag_id falls back to the full fleet.
- Pools: `airflow pools import pools.json` uploaded 2 pools; `warehouse` lists 16 slots. Every one of the 682 tasks reads back pool `warehouse`, weight rule absolute, priority 100 (98 critical tasks) or 1 (584 standard).
- Execution: `airflow dags test` of billing_chargebacks (critical) and billing_carriers (standard) both succeeded, each step once, in dependency order.

**Not verified:** behaviour under a live scheduler and real pool contention (no scheduler locally), and the production DAG processor's own timing. Note the first deploy will create one new version per DAG, since the pool and priority fields change every serialised DAG; after that, versions only change with configs.