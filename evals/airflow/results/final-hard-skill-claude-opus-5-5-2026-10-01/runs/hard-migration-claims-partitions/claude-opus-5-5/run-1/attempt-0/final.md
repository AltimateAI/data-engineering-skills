The claims project is migrated to Airflow 3.3.2, and it writes byte-for-byte the same files as on 2.11. I checked that by replaying the same runs on the untouched project with a real Airflow 2.11.2 venv (one was on this machine) and on the migrated project with 3.3.2, then diffing the output trees. Nothing is committed yet.

**What the replay covered:** 52 runs on each side, all successful, and all 85 output files identical:
- 6 provider snapshots, so the changed/unchanged flag ran past its 3rd run.
- 31 hourly intakes plus a manual one.
- 8 alias-triggered mart rebuilds, created by each version's real scheduler code from the queued events.
- 2 runbook reprocess triggers (`--conf service_date`, no logical date).
- 5 scheduled and 2 manual digests. One digest was deliberately run after a later same-day manual provider snapshot; both versions picked directory version 2026-03-05.

**Changes that would otherwise have altered output silently on 3.x:**
- **All schedules** (`@hourly`, 03:00, 07:00) now use `CronDataIntervalTimetable`. A bare cron on 3.x would have shifted every partition, snapshot and digest by one period. `catchup=False` was already explicit everywhere and is unchanged.
- **`provider_directory_daily`:** added `map_indexes=-1` to the fingerprint lookup. On 3.x it returns a list from the 3rd run on, so `.status` would have said "changed" every day.
- **`denials_digest_daily`:** the cross-DAG XCom pull returns `None` on 3.x. It now reads the provider asset's events and takes the version from the provider run dated latest at or before its own date, which is the same lookup 2.x did. My first attempt (latest snapshot file by date) failed the replay in the late-snapshot case, which is why I switched.
- **`claims_service_date_marts`:** 3.x lists each alias event twice, once under the partition and once under the alias, which would have doubled the new-claim counts in the rebuild records. It now reads each event once through the alias.
- **`claims_reprocess`:** a CLI trigger has no `logical_date` on 3.x. The cutoff, the `received_reprocess_<time>.csv` name and the `_RECHECK_LOG` timestamp now use the trigger time, as on 2.x.
- **Manual UI triggers** of intake, provider and digest also keep their 2.x dates: the latest closed hour for intake, the trigger date for the other two. The runbook doesn't use these.
- **Mechanical:** imports moved to `airflow.sdk` and the standard provider, and `Dataset`/`DatasetAlias` became `Asset`/`AssetAlias` in `plugins/claims_lib`. `requirements.txt` now pins `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`; `pendulum==3.2.0` is kept. Task ids, paths, file names and formats are unchanged.

**Checks:** `ruff --select AIR` is clean on `dags/` and `plugins/`. The schedule preview matches 2.x for every DAG. The skill's DAG checker still reports one error at `denials_digest_daily.py:35`. It's a false positive: that `xcom_pull()` belongs to the asset event's source task, not to the current task.

**Not covered, and worth knowing before next week:**
- The stock replay tooling can't run alias-triggered DAGs, so I wrote my own driver (`$TMPDIR/mig/drive.py`). It uses Airflow's own scheduler function but not a running scheduler, DAG processor and API server. A smoke test on a real 3.3 deployment is still worthwhile.
- The project has no test suite, so there was no pytest run.
- Production needs `plugins_folder=plugins/` on the DAG processor and the workers, as the README already says.
- If `airflow db clean` purges old provider asset events, the digest can lose its directory version. On 2.x, cleaning old XComs had the same effect.
- On both versions, `_RECHECK_LOG` writes fail if `output/marts/` doesn't exist yet. This only happens before the first mart rebuild.