Migration complete. Everything is in the working tree, uncommitted.

**What changed (Airflow 2.11.2 to 3.3.2)**

- **Schedules**: the hourly intake and the two daily DAGs now use `CronDataIntervalTimetable`, so each run keeps processing the hour or day that just ended. A bare cron string on 3.x would have shifted every output by one period. Explicit `catchup=False` values kept.
- **claims_reprocess**: the trigger time comes from `dag_run.logical_date or dag_run.run_after` in the task and in the Bash template. Runbook triggers have no logical date on 3.x, so the old code would have crashed. The runbook command is unchanged.
- **claims_service_date_marts**: reads `triggering_asset_events` once through the alias and takes the partition from the event's asset URI. Airflow 3 also lists each alias event under its partition asset, so the old loop over all keys would have doubled the new-claim counts in the rebuild records.
- **denials_digest_daily**: the directory version is now the latest `output/lake/providers/<day>.csv` dated at or before the service date. The cross-DAG XCom pull returns None on 3.x.
- **provider_directory_daily**: fingerprint pull gets `map_indexes=-1` so it always compares a scalar.
- **plugins**: Dataset and DatasetAlias became Asset and AssetAlias, BaseHook comes from `airflow.sdk`. Imports moved to `airflow.sdk` and the standard provider everywhere.
- **requirements.txt** pins Airflow 3.3.2 and the standard provider 1.19.0. README gained an Airflow 3 notes section and a reminder that workers need the plugins folder too.

**Verified**

- Checker: 0 import errors, 0 errors. Ruff AIR rules clean on dags and plugins.
- Run preview: all five DAGs have identical fire times, logical dates and data intervals before and after.
- Replay of 5 hourly intake runs, 3 provider runs, 3 digest runs and the runbook reprocess trigger, same metadata DB per side: all 16 files that have a 2.11 baseline are byte-identical.
- Reprocess output checked by hand against the 2.11 semantics: file `received_reprocess_20260305T0915.csv` holds the 4 missing claims received before 09:15 and excludes the 09:21 one, and the recheck log line reads `2026-03-03 rechecked at 2026-03-05T09:15:00+00:00: 4 claim(s) recovered`.
- Marts task called with 3.x-shaped events (listed under both asset and alias): counts not doubled, mart totals equal the partition row counts.
- Provider fingerprint on a probe where day 3 equals day 2: statuses first snapshot, changed, unchanged.

**Not verified, and why**

- No 2.x interpreter exists, so the baseline ran the old code on 3.3 with 2.x scheduler defaults. The digest and reprocess runs therefore have no machine baseline. I checked those outputs by hand as above.
- Alias-triggered marts runs cannot be driven by the replay. The task was exercised directly, and the `publish_ready` template is unchanged from 2.11.
- The project has no test suite, so nothing to run there. Manual triggers of the three scheduled DAGs are not in the runbook and were left as they were; on 3.x they would fail on the missing date rather than silently run.