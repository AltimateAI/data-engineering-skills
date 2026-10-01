The code is migrated to Airflow 3.3.2, with a few caveats: the alias-triggered marts DAG and the mart-dependent digest content were not replayed, and the reprocess runbook run has no 2.11 baseline. The checker reports 0 import errors and 0 errors, ruff `AIR` rules pass on `dags/` and `plugins/`, and the schedule preview (5 runs per DAG) matches 2.x exactly for all 5 DAGs. I made no commit; the changes are in the working tree.

**Changes**
- **Schedules:** the three cron DAGs (`claims_intake_hourly`, `provider_directory_daily`, `denials_digest_daily`) now use `CronDataIntervalTimetable(..., timezone="UTC")`. A bare cron string on 3.x would have shifted every run's `ds` by one day. `catchup=False` was explicit everywhere, so it stays.
- **`claims_service_date_marts`:** `triggering_dataset_events` became `triggering_asset_events`. On 3.x each alias event is listed under both the asset and the alias, so the old loop over `.items()` would have doubled the per-partition new-claim counts in the rebuild records. It now reads each event once via the alias.
- **`claims_reprocess`:** a runbook trigger has no logical date on 3.x. The trigger time now comes from `dag_run.run_after`. This sets the `received_reprocess_<yyyymmddThhmm>.csv` file name, the cutoff and the `_RECHECK_LOG` timestamp.
- **`provider_directory_daily`:** the `include_prior_dates` XCom pull returns a list from the 3rd run on, which would have flipped `<day>.status` to "changed" wrongly. I added `map_indexes=-1`.
- **`denials_digest_daily`:** the cross-DAG XCom pull returns `None` on 3.x. It now picks the newest `output/lake/providers/<day>.csv` at or before `ds`, which is the same version 2.x pulled.
- **Plus:** the Asset and `BaseHook` imports, `airflow.sdk` imports, the standard-provider `BashOperator`, and a task variable renamed to match its `task_id`.
- **`requirements.txt`:** pinned `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`. The repo has no tests.

**Replay**
There is no 2.x environment here, so I replayed the original code on 3.x with 2.x scheduler defaults. I ran 4 scheduled runs each of `claims_intake_hourly`, `provider_directory_daily` and `denials_digest_daily`, plus the `claims_reprocess` runbook trigger.
- **`claims_intake_hourly`:** identical output.
- **`provider_directory_daily`:** identical except one status file, `2026-03-05.status`. The original gives "changed", which is the list bug. The migrated code gives "unchanged", which matches 2.x because the directory content is identical to the previous day's.
- **`denials_digest_daily` and `claims_reprocess`:** the original code fails on 3.x, so these have no baseline.

**Not verified**
- **`claims_service_date_marts`:** asset-triggered runs can't be replayed, so the fix is checked only against the documented 2.x vs 3.x behaviour.
- **`claims_reprocess` mart steps:** the trigger-time handling is exercised, but nothing from the marts DAG ran.
- **Digest content:** no mart files existed in the replay, so the digest rows themselves weren't compared.
- **`_RECHECK_LOG`:** the `log_recheck` task failed only because `output/marts/` doesn't exist until the marts DAG has run, which would also fail on 2.x. The rendered command and timestamp format were correct.

Before production, I'd run one real alias-triggered mart rebuild on a 3.x staging instance and compare `output/marts/rebuilds/` and `_READY_PARTITIONS` against 2.11.