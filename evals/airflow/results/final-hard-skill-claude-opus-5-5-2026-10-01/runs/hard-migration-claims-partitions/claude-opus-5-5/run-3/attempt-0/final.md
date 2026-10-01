The project is migrated to Airflow 3.3.2. Replaying the same runs on the real 2.11.2 venv and on 3.3.2 wrote byte-identical files for the scheduled runs and the runbook reprocess. Nothing is committed yet; the changes are in your working tree.

## What changed and why

| DAG / file | Change | Why it was needed (the 3.x behaviour that would have changed outputs) |
|---|---|---|
| `provider_directory_daily`, `denials_digest_daily`, `claims_intake_hourly` | Cron strings replaced with `CronDataIntervalTimetable(...)`. Your explicit `catchup=False` is kept. | On 3.x a bare cron string means `ds` is the day the run fires. Every snapshot, digest and hourly file would have moved one period later. |
| `provider_directory_daily` | `xcom_pull(..., include_prior_dates=True, map_indexes=-1)` | From the 3rd run on, 3.x returns a list of all earlier fingerprints. The `.status` file would then always say "changed" when it should say "unchanged". |
| `denials_digest_daily` | The cross-DAG XCom pull is replaced by "newest `lake/providers/<day>.csv` dated on or before `ds`". | On 3.x that pull returns None because it matches on this run's `run_id`. The new rule is what the README describes and what 2.x returned. |
| `claims_reprocess` | The cutoff time, the `received_reprocess_<…>.csv` name and the `_RECHECK_LOG` timestamp now use the trigger time: `run_after` with microseconds set to zero. | A 3.x CLI trigger without `-e` has no `logical_date` or `ts`. 2.x also zeroed the microseconds (I checked the trigger code in both versions), so the log line keeps the same format. |
| `claims_service_date_marts` | Uses `triggering_asset_events`, reading each event once through the alias. | The old key no longer exists. Also, 3.x lists every alias event twice (under the alias and under the partition), so the old loop would have doubled every new-claims count. |
| `plugins/claims_lib` | `Asset`/`AssetAlias` and `airflow.sdk.BaseHook` | The old imports no longer exist on 3.x. URIs, task ids, paths and file formats are unchanged. |
| `requirements.txt` | `apache-airflow==3.3.2`, `apache-airflow-providers-standard==1.19.0` | `BashOperator` now comes from the providers-standard package. |

I also added something you didn't ask for. If someone triggers the hourly, provider or digest DAG by hand (e.g. from the UI), it now uses the same dates 2.x would have. Without this, 3.x would crash or write a `None.csv`.

## Verification
- **Static checks:** the checker exits 0 and `ruff --select AIR` is clean on `dags/` and `plugins/`. The first 5 scheduled runs of each time-based DAG have the same logical dates and data intervals on 2.11 and 3.3.
- **Replay, real 2.11.2 vs 3.3.2, one database per side:**
  - 6 provider snapshots
  - 10 hourly intake runs
  - 4 digests
  - 2 runbook-style reprocess triggers

  All runs succeeded on both sides and every file under `output/` is identical. That includes the "unchanged" statuses from run 5 onward, the directory version in the digests, the recovered-claims files and `_RECHECK_LOG`.
- **Alias-triggered mart rebuilds, with real schedulers:**
  - **3.3:** 5 rebuild runs, triggered by single intake hours, a batch from two intake hours, and a reprocess. Each of the 11 events was consumed exactly once and every per-partition count is correct.
  - **2.11:** only the first rebuild could be compared, and it is byte-identical (same record file and same READY line). After that, 2.11's task processes hang in this sandbox (a macOS fork problem, not a DAG problem).

## Things you should know
1. **How events are grouped into rebuild records can differ on 3.3.** I saw a mart run start 4 ms into the intake task's event writes. It took 3 of that task's 4 events, and the next run picked up the 4th. Every claim is still counted exactly once and the mart CSVs end up the same. But a single intake hour can occasionally show up as two rebuild records (`0004_…`, `0005_…`) instead of one. On 2.x a task's events were committed all at once. This comes from Airflow itself; the DAG code can't change it.
2. **Not fully verified:** I couldn't run the full sequence of 2.x alias rebuilds (beyond the first) for the sandbox reason above. I also didn't replay manual UI triggers of the scheduled DAGs. And there are no project tests to run; the repo has none.
3. **For go-live:** production needs `apache-airflow-providers-standard` installed. The same `plugins_folder` must be set on the DAG processor and on the workers, because the shared code is imported from there on both.