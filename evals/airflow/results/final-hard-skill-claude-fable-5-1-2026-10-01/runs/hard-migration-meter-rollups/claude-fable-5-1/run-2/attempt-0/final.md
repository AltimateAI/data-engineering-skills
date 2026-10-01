The migration is complete and verified. The project now imports and runs on Airflow 3.3.2, and every scheduled run, both runbook triggers, and the rollup task logic produce byte-identical files to Airflow 2.11.2. Changes are in the working tree, not committed.

**What changed per DAG** (all under `dags/` and `plugins/`)

- **Every cron DAG keeps its 2.x period.** Bare cron strings and presets became `CronDataIntervalTimetable`, so a run still processes the interval that just ended. On 3.x the same string would have shifted every `ds` and data interval forward by one period, which would have billed and synced the wrong day.
- **billing_daily:** a plain `airflow dags trigger` has no data interval on 3.x. The `bill` task now infers the latest closed interval from the trigger time with the core timetable's own rule, so it re-bills the latest closed day exactly as 2.11 did. The template's `conf.get` is restored through `user_defined_macros`.
- **tariffs_daily:** had no `catchup` argument, which meant `catchup=True` on 2.x, so it is now explicit. The shell template no longer uses the removed `tomorrow_ds`. It picks the interval day on scheduled runs and the trigger day on manual runs, then adds one calendar day.
- **usage_rollup:** asset-triggered runs carry no data interval on 3.x. The task rebuilds the same min-to-max window from the source runs' intervals of the triggering events, and reads events keyed by Asset objects instead of URI strings.
- **meter_registry_daily:** `execution_date` became `logical_date`, `provide_context` was removed, and `Variable.get` uses the 3.x `default=` keyword.
- **regional_readings and plugin operator:** interval timetable, Dataset became Asset, `outlet_events` keyed by the asset object, `BaseOperator` from the SDK. The `macros.meter.*` plugin is unchanged and still renders.
- **requirements.txt** pins Airflow 3.3.2 and the standard provider 1.19.0.

**What was verified**

- Checker: 0 import errors, 0 error findings. Ruff AIR rules: clean.
- Preview compare between a true 2.11.2 capture of the untouched repo and the migrated repo: 6 of 6 DAGs match on fire times, logical dates, intervals and catchup.
- Replay of the same plan on 2.11.2 and 3.3.2 against separate metadata DBs: 17 runs per side, identical run dates and identical files. The plan covered 3 consecutive scheduled runs of tariffs, both readings DAGs, registry and billing, plus the two runbook triggers from the README. Both manual runs succeeded on 3.x with no logical date and wrote the same files as 2.x.
- Rollup task function called on both versions with three batched hourly loads per region: identical CSV and manifest.

**Not verified**

- An end-to-end asset-triggered rollup run through a live 3.x scheduler was not replayed. The event delivery shape was checked only at the task-function level with constructed events.
- The replay seeded one identical rollup file on both sides so billing had usage to price, since the rollup could not be produced by the replay itself.
- Manual triggers of the readings and registry DAGs are not in the runbook and were not ported. On 3.x such a trigger would fail to render `data_interval_start`.
- The repo has no test suite, so no pytest run. Deployment config such as the plugins folder on the DAG processor and workers still needs the same setting as before.