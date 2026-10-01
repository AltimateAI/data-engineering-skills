Migration complete and verified. All five DAGs import on Airflow 3.3.2, and a replay of the same run sequence on the untouched 2.11.2 code and the migrated code produced byte-identical output trees. Nothing is committed; the changes sit in the working tree.

**What changed, per DAG**

- **`claims_intake_hourly`, `provider_directory_daily`, `denials_digest_daily`**: the bare cron strings became `CronDataIntervalTimetable`. On 3.x a bare cron is a trigger timetable, so `ds` and the data interval would have shifted one period later and every file would have been named for the wrong day. Explicit `catchup=False` was kept everywhere.
- **`provider_directory_daily`**: the fingerprint pull gained `map_indexes=-1`. Without it, 3.x returns a list of all earlier fingerprints from the third run on, and every day's status file would read "changed".
- **`denials_digest_daily`**: the cross-DAG XCom pull returns None on 3.x (it is matched on this run's run_id). The digest now picks the latest snapshot file dated at or before its day, which is exactly what the XCom resolved to on 2.11. The README was updated to say the snapshot name is the version.
- **`claims_service_date_marts`**: reads events once through the alias key and uses `event.asset.uri`. On 3.x the old loop would have double-counted every partition's new-claim count in the rebuild records, and URI-string keys raise TypeError.
- **`claims_reprocess`**: the runbook trigger has no `logical_date` or `ts` on 3.x. Trigger time now comes from `dag_run.run_after`, so the recovered-claims file name and the recheck log line are unchanged.
- **Plugins**: `Dataset`/`DatasetAlias` became `Asset`/`AssetAlias`, `BaseHook` moved to the SDK, and three small helpers were added so a UI or CLI trigger of a cron DAG keeps the 2.11 meaning (trigger date, latest closed interval).
- **requirements.txt** pins Airflow 3.3.2 and the standard provider.

**What was verified**

- Checker: 0 import errors, 0 errors on `dags/` and `plugins/`. The three remaining warnings are static matches on the parameters whose manual-run fallback sits right below them.
- Ruff with all AIR rules: clean.
- Schedule preview on the real 2.11 env versus 3.3: all 5 DAGs match (same fire times, logical dates, intervals).
- Full replay on 2.11.2 and 3.3.2 against one metadata DB per side: 3 provider snapshots, 3 digests, 13 hourly intakes with one alias-triggered mart rebuild after each, and both runbook reprocess triggers (one recovering a claim from a deliberately skipped intake hour, one recovering none). Every step succeeded on both sides and the 56 output files are identical, including the third snapshot's "unchanged" status, the digest headers, 15 numbered rebuild records and the recheck log.
- A second replay of UI-style manual triggers of the three cron DAGs: 14 identical files.

The stock replay tool cannot create alias-triggered runs, so I wrote a driver that calls each version's own scheduler code to turn queued alias events into the consumer run. The driver, both plans, logs and JSON reports are under `tmp/mig/` in the task directory if you want to rerun them.

**Not verified and worth knowing**

- The replay drives tasks in-process. Production worker isolation on 3.3 was not exercised, but the DAGs touch no metadata-DB sessions.
- Real CLI triggers carry microseconds in the trigger time. Both versions format `ts` identically, and the file name truncates to the minute, so this does not change outputs.
- The project has no test suite, so none was run or added.