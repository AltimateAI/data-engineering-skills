Done. The factory is rewritten, the warehouse pool is defined, and every requirement is verified locally.

**What was wrong**

- Every one of the 140 configs re-parsed the 550 KB registry with the pure-Python loader, so one parse took 76 s on this laptop. That is the import timeout and the 28 s worker parses.
- The start minute came from the built-in `hash()`, which is salted per process, and `doc_md` embedded the wall-clock time. The owner string was built from a set, so its order changed too. Every parse therefore produced a different DAG and a new version.
- One bad YAML raised at module level, so the whole file failed and all 140 DAGs vanished.
- Tasks ran in the default pool with the default downstream weight rule, so a long standard pipeline outranked a short critical one.

**What changed**

- `dags/pipeline_factory.py`: the registry is loaded once per parse with libyaml when available. The minute is crc32 of the pipeline name mod 60, with an explicit `schedule.minute` taking precedence. Owners are deduplicated in a fixed order and the timestamp is gone from the doc. Each config is loaded and built inside its own error boundary that logs the config path and skips only that pipeline. Unknown tier, unknown table, unknown dependency, duplicate step and duplicate dag_id are all caught the same way. When Airflow's parsing context carries a dag_id, only that pipeline's config is read and built. Every task runs in the `warehouse` pool with one slot and `weight_rule="absolute"`, critical pipelines at priority 100 and standard at 1.
- `pools.json`: added the `warehouse` pool with 16 slots.
- `README.md`: documented the pool, priorities, minute derivation and failure behaviour.

**Verification results**

| Check | Result |
|---|---|
| Full parse, libyaml loader | 0.24 s for 140 DAGs |
| Full parse, pure-Python loader | 2.3 s |
| Serialized DAG hashes across two processes with different hash seeds | all 140 identical (old factory differed) |
| Old vs new: dag_ids, tasks, edges, owner sets, retries, hour, days, tags, description | all identical |
| Explicit minutes honoured | all 26 |
| Derived minutes | 57 distinct values, at most 5 pipelines per minute |
| Scratch copy with a bad-YAML, bad-table, bad-tier, bad-dependency and duplicate config plus one new config | 140 original DAGs unchanged hashes, new DAG added, five errors each naming the file |
| Worker mode for billing_carriers | 1 DAG built, identical hash to the processor's |
| Airflow CLI | pools import ok, reserialize lists 140 DAGs, no import errors, `dags test billing_carriers 2026-03-02` ran all 3 steps |

**Two things to know**

- A broken `configs/registry.yaml` still fails the whole file, deliberately, since no pipeline can be validated without it. That shows as a normal import error.
- Prod parse time depends on whether PyYAML there has libyaml. Without it the registry alone costs about 2 s on a laptop, which is still well inside the 30 s timeout.

Nothing under `configs/` was touched, and nothing is committed.