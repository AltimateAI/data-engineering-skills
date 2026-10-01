The factory is fixed and verified. Three files changed: `dags/pipeline_factory.py`, `pools.json`, and a short README note. The registry and pipeline configs are untouched.

**Root causes found in the old factory**

- The 20k-line registry was parsed once per DAG with the pure-Python YAML loader, about 0.5 s each, so 140 DAGs took 74 s per parse on this laptop.
- Start minutes came from Python's salted `hash()`, `doc_md` embedded the current time, and owners were joined from a `set`. Each parse therefore produced different DAGs and a new version.
- Each DAG was built in a `with DAG` block with no error handling, so one bad YAML raised in the loop and the whole file failed to import, taking all 140 DAGs out.
- No pool and the default downstream weight rule, so long standard pipelines outranked short critical ones.

**What the new factory does**

- Loads the registry once per parse with the libyaml loader and indexes teams and datasets from it.
- Picks the minute with a CRC32 of the pipeline name, which is stable across processes and unaffected by other configs. An explicit `schedule.minute` still wins.
- Validates each config as plain data first, with every error message naming the file. It then builds the DAG with `auto_register=False`, passes `dag=` to each operator, validates the cron and runs the cycle check, and only registers DAGs that pass. Failures are logged with `log.error` and `warnings.warn`, and the loop continues.
- Reads the worker's parsing context and, when a DAG id is set, reads only that pipeline's config file. Filenames must equal the dag id, which validation now enforces and which all 140 configs already satisfy.
- Sets `pool="warehouse"`, `weight_rule="absolute"` and `priority_weight` 100 for critical or 1 for standard through `default_args`. The pool is added to `pools.json` with 16 slots and a description.

**Verified in this session**

| Check | Result |
|---|---|
| Parse time, DagBag and `airflow dags report` | 0.22 s and 0.24 s (was 73.9 s) |
| `airflow_check.py` | exit 0, 140 DAGs, 0 import errors, 0 findings |
| Hashes across three `PYTHONHASHSEED` values | all 140 identical |
| Shape vs original file: dag ids, tasks, dependencies, owners, retries, hour, days, descriptions, tags | no differences |
| Explicit minutes honoured | all 26 |
| Implicit minutes | 114 pipelines over 57 distinct minutes, at most 3 share an hour:minute |
| 13 broken configs on a scratch copy (bad YAML, empty, list, bad team, tier, hour, cron, unknown table, unknown upstream, duplicate step, cycle, no steps, name mismatch) | each absent, each named in an ERROR line, no import error, other 140 hashes unchanged |
| Add one config and remove another | the other 139 hashes unchanged |
| Worker context set to one dag id | only that DAG built, hash equals the full-parse hash |
| `airflow pools import pools.json` | both pools imported, warehouse has 16 slots |
| `airflow dags test` on billing_chargebacks (critical) and billing_orders (standard) | success, every step ran once in dependency order |

**Not verified**

- Real scheduler behaviour under pool saturation. There is no scheduler locally, so the priority ordering is confirmed only by reading `pool`, `weight_rule` and `priority_weight` from the built tasks.
- Parse time on the production hosts. On this laptop the file is 130 times under the 30 s import timeout.

One behavioural note: because the old minutes were derived from a salted hash, they already changed on every parse. The new minutes are stable from now on but are not the ones any given parse happened to show before.