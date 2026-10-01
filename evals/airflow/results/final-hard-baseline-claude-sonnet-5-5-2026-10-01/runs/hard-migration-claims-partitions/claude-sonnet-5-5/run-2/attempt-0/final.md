I've migrated all five DAGs and the shared plugin code to Airflow 3.3.2, but I haven't run anything against 2.11 to compare outputs. I ran each DAG on 3.3.2, using the `data/` CSVs and a real scheduler. I did not run the daily digest, and the hourly intake produced files only for the one hour I ran. Nothing is committed.

**Changes that keep the output identical**
- **Cron schedules:** in Airflow 3, `@hourly` and the cron strings now default to a trigger-style timetable. That would shift `ds` and the data interval, so the provider snapshots, digest dates and hourly file names would all be off. I pinned `CronDataIntervalTimetable(..., timezone="UTC")` on the hourly, 03:00 and 07:00 DAGs. After that, the next-run intervals Airflow computes for them match 2.11.
- **`claims_reprocess`:** manual runs now have no logical date, so the cutoff, the `received_reprocess_<yyyymmddThhmm>.csv` name and the `_RECHECK_LOG` timestamp now use `dag_run.run_after`, which is the trigger time. I triggered it with `airflow dags trigger --conf …` and it wrote the expected file and log line.
- **Marts DAG:** in Airflow 3, `triggering_asset_events` lists each event under both the partition asset and the alias. Summing over everything would have doubled the `new_claims` counts in the rebuild records. It now counts only the concrete asset keys. In my scheduler run, the rebuild record, mart CSVs and `_READY_PARTITIONS` came out as expected.

**Mechanical changes**
- **Imports and renames:** imports moved to `airflow.sdk`, with `BashOperator` from the standard provider. `Dataset`/`DatasetAlias` became `Asset`/`AssetAlias`. `schedule_interval` became `schedule`.
- **Dependencies:** `requirements.txt` now pins `apache-airflow==3.3.2` and adds the standard provider.

**One addition you didn't ask for:** the reprocess log task now runs `mkdir -p` on the marts directory before appending. It failed in my first test on a fresh checkout, and the marts DAG normally creates that directory, so production shouldn't see a difference.

**Before cutover**
- In production, the `claims_export` connection needs to resolve for task workers. In 3.x the env-var connection must be set where tasks run, not just on the scheduler.
- Existing 2.11 dataset events and XCom history won't carry over automatically. After the upgrade, the first `provider_directory_daily` run reports "first snapshot" if the old XComs aren't migrated. The first digest also needs a directory snapshot to exist.

I left the helper name `partition_dataset` as it was. The README is unchanged.