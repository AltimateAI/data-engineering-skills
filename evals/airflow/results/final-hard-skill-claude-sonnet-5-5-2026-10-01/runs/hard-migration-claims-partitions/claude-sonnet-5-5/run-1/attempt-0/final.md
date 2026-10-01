The migration is done and in the working tree (uncommitted), but only the scheduled runs are proven identical to 2.x. The alias-triggered marts DAG has not been run on 3.3. The `claims_reprocess` manual run and `denials_digest_daily` were checked by hand, not against a 2.x baseline.

**What I changed (Airflow 2.11.2 → 3.3.2)**
- **Schedules:** all time-scheduled DAGs now use `CronDataIntervalTimetable(..., timezone="UTC")`. A bare cron string would have moved every date by one period on 3.x. The preview comparison of run dates and intervals shows no difference. Their explicit `catchup=False` is kept.
- **`claims_intake_hourly`:**
  - Hourly cron timetable.
  - Imports moved to `airflow.sdk`.
  - Dataset/DatasetAlias became Asset/AssetAlias in `plugins/claims_lib/assets.py`.
- **`claims_service_date_marts`:**
  - It now reads `triggering_asset_events[CLAIMS_BY_SERVICE_DATE]` and counts each event once via `event.asset.uri`. Looping over the old structure would double-count on 3.x.
  - The task variable `publish` is renamed `publish_ready` to match its `task_id`.
- **`provider_directory_daily`:** the previous-run fingerprint lookup now uses `map_indexes=-1`. Without it, from the 3rd run on, the "changed/unchanged" status would flip wrongly.
- **`denials_digest_daily`:** the cross-DAG XCom lookup returns `None` on 3.x. It now picks the latest `output/lake/providers/<day>.csv` dated at or before the run's `ds`, which is what 2.x returned.
- **`claims_reprocess`:**
  - A runbook trigger has no `logical_date` on 3.x. The task and the `_RECHECK_LOG` timestamp now use the trigger time (`logical_date or run_after`), the same value 2.x used.
  - `received_reprocess_<yyyymmddThhmm>.csv` and `_RECHECK_LOG` keep their names and formats.
- **Hook and requirements:** `BaseHook` comes from `airflow.sdk`. `requirements.txt` is pinned to `apache-airflow==3.3.2` plus `apache-airflow-providers-standard==1.19.0`.

**What I checked**
- The project checker exits 0 with no import errors or error findings. `ruff --select AIR` is clean on `dags/` and `plugins/`.
- Scheduled run dates, intervals and `catchup` for the four time-scheduled DAGs match the 2.x defaults.
- I replayed 4 daily provider runs and 30 hourly intake runs on both sides. They wrote identical files.
- The digest runs and the `claims_reprocess` runbook trigger (`--conf '{"service_date":"2026-03-05"}'`, trigger time 09:15Z) succeeded on 3.3.
- Their outputs look right: digests name the correct directory version, and the `_RECHECK_LOG` line carries the trigger time as an ISO timestamp.

**What I did not verify**
- **No 2.x environment:** the "before" side ran on 3.3 with the 2.x scheduler defaults, so it only reproduces 2.x schedule dates. Digest and reprocess have no replay baseline. I compared them by hand against the 2.11 behaviour documented in the migration skill's reference.
- **`claims_service_date_marts`:** asset-triggered runs can't be replayed here, so I never ran its new event-reading code. The rebuilt mart files, numbered rebuild records and `_READY_PARTITIONS` lines are untested. I'd run it against a staging deployment, since that is what BI relies on.
- **Deployment settings:** I assumed production never overrode `catchup_by_default` or the cron/delta interval settings. The explicit `catchup=False` on every DAG makes that mostly moot, but check the 2.11 config.
- **Existing tests:** the repo has no tests.
- **Environment:** `plugins_folder` must be set on the 3.x DAG processor and workers, and `AIRFLOW_CONN_CLAIMS_EXPORT` stays as in the README.

I haven't committed anything.