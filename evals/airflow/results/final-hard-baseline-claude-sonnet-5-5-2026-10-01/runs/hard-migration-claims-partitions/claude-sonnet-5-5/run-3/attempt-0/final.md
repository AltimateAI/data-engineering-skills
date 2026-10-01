I've migrated all five DAGs and the shared plugin code to Airflow 3.3.2. I couldn't run the full chain end to end, so the alias-triggered mart rebuild and the scheduled digest lookup are only partly verified. The changes are uncommitted.

**How I checked it.** The local scheduler and API server wouldn't run properly in my sandbox, so I used `airflow dags test` for the intake, provider directory and reprocess DAGs. The mart rebuild and the digest lookup were exercised with stand-ins, so please run a real scheduled day on a staging 3.3 before the cutover.
- **Intake, provider directory, reprocess:** these ran and wrote the expected files, including `received_20260304T20.csv` for the 21:00 run and `received_reprocess_<time>` for the reprocess.
- **Mart rebuild:** I fed the task a hand-built event list and it wrote the right mart CSV and numbered rebuild record (`{"2026-03-02": 5, "2026-03-04": 3}`).
- **Digest lookup:** I confirmed the new cross-DAG XCom pull works with a stand-in DAG, but the digest itself never ran against a real scheduled provider run.
- **Not run:** `_READY_PARTITIONS` and the BI-visible digest output, since they need a real alias-triggered and scheduled run.

**Behaviour changes in 3.x that would have altered output silently, and what I did about them:**
- **Schedules:** `schedule_interval` is gone, and a plain cron string in 3.x no longer means "run for the interval that just ended". It would have shifted the hourly partition file names, the provider snapshot day and the digest day by one period. I set `CronDataIntervalTimetable(..., timezone="UTC")` on the hourly, 03:00 and 07:00 DAGs so the intervals are the same as on 2.11.
- **Reprocess trigger time:** manual triggers now have no logical date, which the runbook already assumes. The task would have crashed on it. I use `dag_run.run_after` (the trigger moment) for the cutoff, the `received_reprocess_…` file name and the `_RECHECK_LOG` timestamp.
- **Mart rebuild:** the triggering events now include the alias itself as a key. Unfiltered, that would have duplicated the claim counts and crashed on the URI. I skip anything that isn't an `Asset`, and the rebuild records come out the same.
- **Digest directory version:** 3.x can't pull another DAG's XCom with `include_prior_dates` (it returns nothing), so the digest would have failed on a missing `None.csv`. It now walks back through `provider_directory_daily`'s scheduled run ids (`scheduled__<day>T03:00:00+00:00`, up to 90 days) and takes the latest version.
  - Manually triggered provider runs are no longer considered. On 2.11 they could be picked up.
  - If the provider schedule changes from 03:00, `latest_directory_version` has to change with it.

**Mechanical changes:**
- Imports moved to `airflow.sdk` (`dag`, `task`, `Param`, `BaseHook`, `Asset`, `AssetAlias`).
- `BashOperator` now comes from `airflow.providers.standard`.
- `triggering_dataset_events` is now `triggering_asset_events`.
- `requirements.txt` pins `apache-airflow==3.3.2` and adds the standard provider.
- The asset URIs and the alias name are unchanged.

**Not changed:**
- **`_RECHECK_LOG`:** it still fails if `output/marts/` doesn't exist yet, as on 2.11.
- **Triggering other DAGs by hand:** manually triggering the interval DAGs without a logical date would break their `ds` and data-interval values, as it effectively did before.

**Before cutover:**
- **XCom state:** the fingerprint and version XComs from 2.11 are only carried over if you migrate the metadata database.
- **First run:** otherwise the first provider run reports "first snapshot", and the digest needs a provider run on or before its date.