I've migrated the project to Airflow 3.3, and on a real local 3.3.2 instance with the sample data every DAG produced the outputs it would on 2.11. I haven't committed anything; the changes are in your working tree. I had no 2.11 install to compare against, so I checked the 3.3 outputs against the data and against the 2.11 logic by hand.

**Plain renames:** imports now come from `airflow.sdk` (`dag`, `task`, `Asset`, `AssetAlias`, `Param`, `BaseHook`), `BashOperator` comes from the standard provider, and `schedule_interval` became `schedule`. `requirements.txt` now pins `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`.

**Changes that would otherwise have altered outputs on 3.3:**
1. **Cron schedules (intake, provider directory, digest).** Airflow 3 runs cron strings with a different scheduler, which would have made every hourly intake run an empty window (nothing landed) and shifted the daily `ds` forward a day. All three now set the 2.11 behaviour explicitly with `CronDataIntervalTimetable(..., timezone="UTC")`.
2. **Marts DAG (`claims_service_date_marts`).** Airflow 3 lists each triggering event under its partition and again under the alias, so new claims would have been counted twice. It now counts only the partition entries.
3. **`claims_reprocess` from the runbook.** A trigger with no logical date now has no `logical_date` and no `{{ ts }}`, so the task would crash and the log line would break. A small `trigger_time` helper uses the trigger time with microseconds dropped, as 2.11 did. The cutoff, the `received_reprocess_<yyyymmddThhmm>.csv` name and the `_RECHECK_LOG` line come out exactly as before.
4. **Provider directory status.** Pulling the previous fingerprint now returns every earlier value instead of the latest, so every day would have said "changed". Adding `map_indexes=-1` restores "latest only".
5. **Denials digest.** In 3.3 the digest's pull of the directory version from the other DAG returns nothing; I confirmed this against the database. The digest now takes the latest provider snapshot dated on or before its own date (both the `.csv` and its `.status` must exist). That is the same version the old XCom gave, because the version was the snapshot's day.

**Test results:**
- **Provider directory:** snapshots for 03-01 to 03-06 were written with the right days. The statuses were first snapshot, changed, changed, changed, unchanged, unchanged.
- **Intake:** all 64 claims landed in their hourly files.
- **Mart rebuilds:** 18 alias-triggered runs fired. The new-claim counts in the rebuild records add up exactly to what's in the lake, with no double counting, and the mart CSVs match.
- **Digests:** each used the directory for its own day.
- **Reprocess:** I deleted one lake file and ran the exact runbook command. It recovered that one claim, rebuilt only that day's mart (back to identical numbers), and wrote record `0020_…` plus the log line `2026-03-04 rechecked at 2026-10-01T14:08:22+00:00: 1 claim(s) recovered`.

I shut down the test instance and deleted the generated `output/`.

**Before next week:**
- **Manual triggers of the other DAGs:** `airflow dags trigger` with no logical date now produces a run with no dates. The runbook's reprocess is handled, but a manual run of the provider, digest or intake DAGs would need `--logical-date` (or use `airflow backfill create`). If ops ever trigger those by hand, that needs adding to the runbook.
- **Upgrade the metadata database** in production with `airflow db migrate` rather than starting fresh, so the "previous snapshot" comparison still sees the 2.11 run history. The digest only needs the snapshot files in `output/lake/providers/`.