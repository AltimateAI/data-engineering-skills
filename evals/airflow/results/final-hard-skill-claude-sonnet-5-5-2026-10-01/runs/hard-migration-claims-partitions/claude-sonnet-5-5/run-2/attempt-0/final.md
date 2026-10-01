The five DAGs and the shared plugin code now run on Airflow 3.3.2, but I could only partly prove the outputs match 2.11. I changed nothing beyond the files below and haven't committed anything.

**What I checked**
- **Checker and lint:** the checker exits 0 on `dags/` and `plugins/`, and ruff's AIR rules pass.
- **Schedule preview:** fire times, logical dates, data intervals and `catchup` match what 2.11 gave for all five DAGs.
- **Replay:** I ran the intake, provider directory, digest and reprocess DAGs on the old code (3.3 with the 2.x scheduler defaults) and the migrated code, then compared output files. The run covered four scheduled runs of each scheduled DAG and two reprocess triggers. The run dates and every file under `output/` matched wherever the old side could run.
- **No 2.x environment:** there isn't one locally, so none of this is a true 2.11 baseline.
- **Tests:** the repo has no tests, so none ran.

**Not verified**
- **Mart rebuilds:** the alias-triggered `claims_service_date_marts` can't be replayed without real events. That covers the rebuild files, the numbered rebuild records and `_READY_PARTITIONS`. I changed it by following the documented 3.x behaviour.
- **Reprocess runs:** the old code can't run the reprocess DAG on 3.x, so there was no comparison for the reprocess output files. The `_RECHECK_LOG` lines from the migrated code read `<service_date> rechecked at 2026-03-05T09:15:00+00:00: N claim(s) recovered`. That is the 2.x timestamp format. Please check one real runbook trigger before cutover.
- **Digest runs:** the same applies to the digest DAG, because its old cross-DAG lookup returns nothing on 3.x.
- **Replay setup:** I created an empty `output/marts/` in both replay copies, because the reprocess log append fails without that directory. Production has it from the mart DAG.

**What changed**
- **Imports:** DAGs and plugins now use `airflow.sdk` (plus the standard provider for `BashOperator`), and `Dataset`/`DatasetAlias` became `Asset`/`AssetAlias`.
- **Schedules:** the hourly, 03:00 and 07:00 DAGs now use explicit interval schedules (`CronDataIntervalTimetable`, UTC), so run dates stay the same as on 2.11. A bare cron string on 3.x would have shifted every output by one period.
- **Catchup:** every DAG already set `catchup` explicitly, so none needed changing.
- **`provider_directory_daily`:** the "changed / unchanged" check reads the previous fingerprint with `map_indexes=-1`. Without it, from the third run on that check would always say "changed".
- **`denials_digest_daily`:** it can no longer pull the provider DAG's XCom across DAGs, because that returns nothing on 3.x. It now picks the latest `output/lake/providers/<day>.csv` dated on or before the run's date. This matches what 2.x did as long as the provider job has written a file for each day.
- **`claims_service_date_marts`:** it reads the triggering events once through the alias. Looping over all of them would double-count new claims on 3.x. I also renamed the `publish` task variable to `publish_ready` to satisfy a lint rule; the task id is unchanged.
- **`claims_reprocess`:** runbook triggers have no logical date on 3.x, so the cutoff, the `received_reprocess_<yyyymmddThhmm>.csv` file name and the `_RECHECK_LOG` timestamp now come from the trigger time (`run_after`).
- **`requirements.txt`:** pinned `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.

**Before cutover**
- The README runbook is still accurate.
- On 3.x the worker needs the same plugins folder as the DAG processor.