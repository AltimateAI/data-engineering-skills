I've migrated the claims project to Airflow 3.3.2 and all five DAGs parse. I couldn't run the full scheduler path, so a few behaviours are checked by reading the source or by a stub rather than a real run. Nothing is committed.

**Verified:**
- **Per-DAG runs:** with `airflow dags test`, `provider_directory_daily` (three days, with `.status` files), `claims_intake_hourly` and `denials_digest_daily` all ran.
- **Reprocess:** `claims_reprocess` also ran, and `_RECHECK_LOG` and the `received_reprocess_<trigger time>.csv` file looked right.
- **Marts rebuild:** I ran the rebuild step by hand with stub trigger events. The mart CSV and numbered rebuild record came out as expected.

**Not verified:**
- **Scheduler path:** a real alias-triggered run and a real `airflow dags trigger` with no logical date. My scheduler attempt failed in the sandbox. `dags test` always sets a logical date, so the no-logical-date path rests on `run_after` existing in the Airflow 3 task SDK.
- **Baseline comparison:** there's no 2.11 install, so I couldn't diff outputs against 2.11. The checks above only show the 3.x output looks right.

**What changed because behaviour would otherwise differ:**
- **Cron schedules:** Airflow 3 turns `schedule_interval="@hourly"` or a cron string into a point-in-time schedule by default. That changes `data_interval_*` and `ds`, so the partition and file names would have shifted. All three cron DAGs now use `CronDataIntervalTimetable(..., timezone="UTC")`.
- **Reprocess trigger time:** a manual trigger has no logical date in 3.x, and the DAG used it as the trigger time. The cutoff, the `received_reprocess_<yyyymmddThhmm>.csv` name and the `_RECHECK_LOG` timestamp now come from `dag_run.logical_date or dag_run.run_after`. The log line prints the same ISO format `{{ ts }}` did.
- **Marts rebuild:** the triggering events in 3.x are keyed by both each partition asset and the alias. The old loop would have crashed on the alias key and double-counted `new_claims`. It now counts only `Asset` keys.
- **Denials digest:** in 3.x, `xcom_pull(dag_id="provider_directory_daily", include_prior_dates=True)` returns nothing when pulling from another DAG. On the first test the digest failed trying to open `None.csv`. The digest now picks the latest `output/lake/providers/<day>.status` at or before `ds` and uses that day as the version. It raises a clear error if there is none.

  The `.status` file is written just before the XCom push, so a provider run that failed after writing it could be picked up where the XCom lookup wouldn't have.
- **Imports and packaging:**
  - Imports moved to `airflow.sdk` (`dag`, `task`, `Param`, `BaseHook`, `Asset`, `AssetAlias`).
  - `BashOperator` now comes from `airflow.providers.standard`.
  - The context variable is `triggering_asset_events`.
  - `requirements.txt` pins `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.
- **README:** I added two short notes on the reprocess trigger time and the explicit timetables.

Before cutover, I'd trigger `claims_reprocess` and run one real intake-to-marts cycle on a 3.3 staging scheduler. Existing production XCom history isn't consulted any more by the digest, and the intake-to-marts alias path is the part I couldn't exercise here.

I also removed the `output/` folder my test runs created. The sandbox blocked `<tmp>`, so my test state is in the provided `agent-airflow-home`, outside the repo. I added an `env.sh` one level above the repo with the plugins folder and connection settings used locally.