# DAG factories and generated DAGs

Read this when one file builds many DAGs or many tasks from config (YAML, JSON, a registry, a list
of tables), or when the problem is slow parsing, DAGs that vanish or appear half-built, a new DAG
version on every parse, or shared-resource limits across many DAGs. Facts marked *3.3* were checked
on Airflow 3.3.2 by building DAGs with a real `DagBag`.

## 1. A broken config must take out only its own DAG

Three facts make the obvious `try/except` around each DAG insufficient (*3.3*):

1. **A DAG built in a `with DAG(...)` block (or by `@dag`) registers itself when the block exits,
   even if the block raised.** A `try/except` around the block catches the error and still leaves
   a half-built DAG in the bag. For example, a duplicate step raises `DuplicateTaskIdFound` after
   the first tasks exist.
2. **Some errors are only detected when the DagBag validates the DAG, after your loop has
   finished.** An invalid cron gives `AirflowTimetableInvalid: [0 25 * * *] is not
   acceptable`, and a dependency cycle gives `AirflowDagCycleException`. You can't catch these
   inside the loop. They become an import error for the **whole factory file**, and the error
   names the cron or the DAG, not the config file. **`dag.validate()` does not detect cycles**
   (*3.3*: a two-task cycle passed `validate()`). Call `dag.check_cycle()` yourself (2.x: `check_cycle(dag)` from `airflow.utils.dag_cycle_tester`), and call
   `timetable.validate()` for the cron.
3. **`DagBag` collects every `DAG` object it finds in the module's globals**, including one a
   leftover loop variable still points to. With `auto_register=False`, a rejected DAG left in
   `dag = ...` at module level still broke the whole file.

The pattern that isolated every case (bad cron, cycle, duplicate task, an exception halfway
through the build):

```python
log = logging.getLogger(__name__)

def build(cfg: dict, source: Path) -> DAG:
    """Validate the config as data, then build a DAG that is not registered yet."""
    timetable = CronTriggerTimetable(cron_for(cfg), timezone=cfg.get("tz", "UTC"))
    timetable.validate()                                    # raises AirflowTimetableInvalid
    dag = DAG(dag_id=cfg["name"], schedule=timetable, start_date=START, auto_register=False,
              default_args=default_args_for(cfg), tags=sorted(cfg.get("tags", [])))
    tasks = {}
    for step in cfg["steps"]:
        tasks[step["id"]] = make_task(step, dag=dag)       # pass dag=, no `with` block
    for step in cfg["steps"]:
        for upstream in step.get("after", []):
            tasks[upstream] >> tasks[step["id"]]           # KeyError for an unknown step
    dag.validate()                                          # does NOT check for cycles
    dag.check_cycle()                                       # raises AirflowDagCycleException
    return dag

for path in sorted(CONFIG_DIR.glob("*.yaml")):
    try:
        built = build(load_config(path), path)
    except Exception as exc:                                # one bad file must not stop the rest
        log.error("Skipping DAG config %s: %s: %s", path.name, type(exc).__name__, exc)
        warnings.warn(f"DAG config {path.name} rejected: {exc}")   # shown as a parse warning
        continue
    globals()[built.dag_id] = built
built = None                                                # no module-level reference left
```

- Validate everything you can as data first, before any DAG object exists: required keys, types,
  allowed values, references to other registries, unique step ids, known upstream ids, and
  cycles. Cycles can be found with a topological sort of the config, or left to
  `dag.check_cycle()`. Each check should raise an error that names the config file.
- `log.error(...)` reaches the DAG processor log. `warnings.warn(...)` is also recorded by the
  DagBag (`captured_warnings`, *3.3*).
- A YAML syntax error is just another exception from `load_config`. Read each file inside the
  `try`.
- To prove it works, copy one config, break it in each way (bad YAML, empty file, unknown key,
  unknown upstream, cycle, bad cron, duplicate step), parse, and check three things: the other
  DAGs are all present and their hashes are unchanged (section 2), the broken DAG is absent, the
  file has no import error, and **each** broken file's name appears in the parse output (an error
  caught only by the DagBag shows up as an import error that names no config). Then delete the
  broken copies.

## 2. Every parse must produce the same DAGs

The DAG processor re-parses the file every few seconds, in a new process. Any value that differs
between processes or over time creates a new DAG version on every parse:

| source of churn | stable replacement |
|---|---|
| `hash(name) % 60` (salted per process by `PYTHONHASHSEED`) | `zlib.crc32(name.encode()) % 60` or `int(hashlib.md5(name.encode()).hexdigest(), 16) % 60` |
| iterating a `set` (`",".join(set(owners))`, `for t in set(tables)`) | `sorted(set(items))`, or `list(dict.fromkeys(items))` to keep file order (this also de-duplicates, avoiding `DuplicateTaskIdFound`) |
| `datetime.now()`, `date.today()` or a random value in `doc_md`, `description`, `start_date`, `tags`, `params`, defaults | fixed values; put dates in templates or task code |
| directory listing order, dict built from an unordered source | `sorted(...)` |
| a value derived from the config's position in the list (index-based minutes) | derive it from the config's own name, so adding or removing a file changes nothing else |

To check, parse in two processes with different hash seeds (and, if the code reads the clock, at a
different time), then compare the serialized hash of every DAG (*3.3*: `hash(name)` changed every
DAG's hash between seeds; `zlib.crc32` did not):

```python
# dag_hashes.py — run twice: PYTHONHASHSEED=1 python dag_hashes.py dags/ ; PYTHONHASHSEED=2 ...
import json, sys, time
from airflow.dag_processing.dagbag import DagBag                  # 3.2+; 2.x/3.0/3.1: airflow.models.dagbag
from airflow.serialization.serialized_objects import DagSerialization   # 3.x
from airflow.models.serialized_dag import SerializedDagModel
t0 = time.perf_counter(); bag = DagBag(dag_folder=sys.argv[1]); parse_s = time.perf_counter() - t0
print(json.dumps({"parse_s": round(parse_s, 2), "import_errors": sorted(bag.import_errors),
                  "hashes": {d: SerializedDagModel.hash(DagSerialization.to_dict(g))
                             for d, g in sorted(bag.dags.items())}}))
```

## 3. Parse-time budget

The import timeout (`dagbag_import_timeout`, 30 s by default) applies to the **whole file**.
Workers also parse the file before running each task.

- Measure the file, not a function: use `airflow dags report` (per-file duration) or `parse_s`
  from the snippet above. Measure the median of three parses, at the config volume production has.
- Load shared inputs (a registry or lookup file) **once per parse**, at module level or in an
  `functools.lru_cache`d loader, never once per DAG. For YAML use `yaml.load(f,
  Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))`: the libyaml loader is many times faster.
  Index the registry into a dict once.
- No network, DB, `Variable.get` or subprocess at parse time (SKILL.md, step 3).
- **Single-DAG builds on workers**: `from airflow.sdk import get_parsing_context` (2.x:
  `airflow.utils.dag_parsing_context`). When `get_parsing_context().dag_id` is set, build only the
  config whose DAG id matches (*3.3*: with `_AIRFLOW_PARSING_CONTEXT_DAG_ID` set, only that DAG was
  built, and its hash matched the full parse). Map DAG id to config file name cheaply, without
  loading every config. The skipped path must not change how the matching DAG is built: no
  index-dependent values, and the same shared data.

## 4. Shared resource limits and priorities across DAGs

- **A limit across the whole fleet is a pool**, not `max_active_tasks` (per DAG) or
  `max_active_runs`. Set `pool="name"` on every task that uses the resource, through
  `default_args` or the task factory. Make sure the pool exists in every environment:
  `airflow pools import pools.json` with
  `{"name": {"slots": 8, "description": "...", "include_deferred": false}}`. `slots` and
  `description` are required; without `description` the import fails with
  `Failed to update pool(s)` (*3.3*). Use `pool_slots=` for tasks that take more than one slot.
- **Priority between tiers needs `weight_rule="absolute"`.** The default rule, `downstream`, makes
  a task's effective weight its own `priority_weight` plus the weights of all its downstream
  tasks. So a long low-priority pipeline outranks a short high-priority one. With `absolute`, the
  weight is exactly the `priority_weight` you set. Pick values with a gap between tiers (for
  example 100 for the top tier and 1 for the rest), and set them on every task, via `default_args`.
- Spread start times with a stable value derived from the DAG's name (section 2). Let an explicit
  minute or hour in the config win.

## 5. Generated tasks inside one DAG

- Build the task list as `sorted(set(items))` (or `list(dict.fromkeys(items))`). Duplicate entries
  raise `DuplicateTaskIdFound`, and set order changes the DAG on every parse.
- Read the list from a file deployed with the DAGs, not from a service at parse time. If it must
  come from a service, have a task or CI job write a snapshot file that the DAG reads.
- Task ids must be valid (letters, digits, `_ . -`, at most 250 chars). Sanitise names from config
  in a deterministic way.
- Use dynamic task mapping (`.expand()`) when the list is only known at run time. Generate tasks at
  parse time only when the list changes with deploys.

## 6. Verify a factory

1. `airflow_check.py dags/`: exit 0, the expected number of DAGs, no import errors.
2. Hash stability across two seeds, and a later clock if the code reads it (section 2).
3. The broken-config matrix (section 1).
4. Add one config and remove another. No other DAG's hash may change.
5. Parse time at production volume, and with the parsing context set to one DAG id (section 3).
6. Pools import and every task's `pool`, `weight_rule` and `priority_weight` (read them from the
   DagBag).
7. `airflow dags test` of two generated DAGs, one per tier, and check that the steps run once each,
   in dependency order.
