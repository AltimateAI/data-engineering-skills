The migration is complete and verified. The working tree has the ten modified files, uncommitted, and nothing else.

## Verification

I ran the same operational timeline against a pristine 2.11 copy of the project (in the 2.11 venv found in the cache) and against the migrated code on 3.3.2: six provider snapshots, 32 hourly intake runs with two deliberately skipped hours, 36 alias-triggered mart rebuilds, six digests, and three runbook `claims_reprocess` triggers. All 123 output files are byte-identical between the two, with only the wall-clock trigger timestamps in the reprocess file names and recheck log normalised. The run scripts and both output trees are kept outside the repo under `../parity/` if you want to inspect them.

## What actually changed in 3.3, and how it is handled

Four behaviour changes would have altered the files. Each is pinned in code rather than left to deployment config.

- **Cron strings now mean `CronTriggerTimetable`.** On 3.3 a bare cron string makes the logical date the fire time and the data interval empty, so `ds` shifts a day and the hourly intake lands nothing. The three scheduled DAGs now declare `CronDataIntervalTimetable(..., timezone="UTC")` explicitly, which reproduces the 2.11 semantics regardless of the `create_cron_data_intervals` setting.
- **Manual runs have no logical date.** `airflow dags trigger` without a date leaves `logical_date` empty and records the request time in `run_after`, so `ts` and `logical_date` in `claims_reprocess` would have failed. A small `trigger_time()` helper in `claims_lib` uses the logical date when one is given and `run_after` otherwise, truncated to the second as the 2.11 CLI did. The cutoff, file name and recheck-log line are unchanged.
- **Cross-DAG `include_prior_dates` XCom pulls no longer match.** The 3.3 query correlates the run lookup with the pulled DAG's own runs, so the digest's lookup of the provider directory version returned nothing. `denials_digest_daily` now resolves the version from the `PROVIDERS` asset events (one per successful snapshot), picking the newest version at or before the digest date. New events carry the version in their extra; events migrated from 2.11 fall back to that run's XCom. I tested the fallback by stripping the extra from older events and re-running digests, and the files were unchanged.
- **Alias-routed events appear twice in `triggering_asset_events`.** 3.3 lists them under the partition asset and under the alias, so the mart rebuild only counts the asset keys to avoid double-counting new claims.

A fifth, subtler one surfaced only through the comparison. The provider DAG's own prior-fingerprint pull returned an older fingerprint on 3.3 because the default "all map indexes" lookup path drops the logical-date ordering. Passing `map_indexes=-1` keeps it on the ordered single-value path. Without this, two `.status` files read "changed" instead of "unchanged".

## Mechanical changes

- Imports moved to `airflow.sdk` (`dag`, `task`, `Asset`, `AssetAlias`, `BaseHook`, `Param`, `CronDataIntervalTimetable`) and `BashOperator` to the standard provider.
- `schedule_interval` became `schedule`; datasets became assets (`partition_asset`, same URIs, so migrated 2.11 asset rows match).
- `requirements.txt` pins `apache-airflow==3.3.2` and the standard provider; README gains an "Airflow 3 notes" section and a note on the reprocess trigger time.

## Things to know before cutover

- The runbook command is unchanged. Passing `--logical-date` still works and makes that date the trigger time, as on 2.11.
- The first digests after migration will do one XCom lookup per pre-migration `PROVIDERS` event, since those events lack the version extra. The count is fixed from cutover onward, so the cost is bounded but noticeable on the first runs if the history is long.
- I could not test `airflow standalone` in the pre-provisioned Airflow home because of a port clash; the 3.3 stack ran on a separate home and port. Nothing in the DAG code depends on that.