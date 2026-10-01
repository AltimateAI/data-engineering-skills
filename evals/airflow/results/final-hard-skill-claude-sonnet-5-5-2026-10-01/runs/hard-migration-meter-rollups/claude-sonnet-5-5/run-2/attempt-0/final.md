The project is migrated to Airflow 3.3.2, but I could only prove part of it. All six DAGs import cleanly. The migrated project matches 2.x for schedule dates, but there was no 2.x environment to compare file outputs against. I haven't committed anything.

**What I checked**
- **Schedules:** the 3.3 schedule preview matches the 2.x one for all six DAGs (same run dates, data intervals and catchup), and the checker and `ruff --select AIR` pass.
- **Replay:** I replayed 3 scheduled runs of each time-scheduled DAG, plus the two runbook triggers for `billing_daily` and `tariffs_daily` and a manual trigger of `meter_registry_daily`.
- **Why that isn't proof:** the original code fails on 3.x, so there was nothing to diff the replay's 32 outputs against. I checked them by hand against the 2.x rules instead:
  - **`tariffs_daily` manual trigger at 03-05 09:15:** wrote 03-05 and 03-06, as 2.x did.
  - **`billing_daily` manual trigger at 03-05 09:15:** re-billed 03-04, the latest closed day.
  - **`meter_registry_daily` manual trigger:** `as_of` is the trigger time.
  - **Scheduled runs:** the dates match 2.x.
- **`usage_rollup`:** I did not replay it, because asset-triggered runs can't be replayed here. I ran its task function once with fake events, and it produced the expected file name (`usage_20260302T00_20260302T02`) and manifest. It has never run against real asset events. The same applies to alias handling, which doesn't apply here since there are no aliases.
- **Not run:** there are no project tests, so none were run. I didn't try a real `airflow dags trigger` or REST call either; the manual runs went through the replay script.

**Behaviour kept the same**
- **Time-scheduled DAGs:** each uses an explicit interval timetable, so `ds` and the data intervals keep their 2.x values. A bare cron string on 3.x would have shifted every output by one period.
- **`tariffs_daily` catchup:** it had no `catchup` setting, so it ran as `catchup=True` on 2.x. I set that explicitly (3.x defaults to False). When it is unpaused it will create about 212 runs back to its 2026-03-03 start date, as on 2.x.
- **Runbook triggers:** `plugins/meter_lib/windows.py` is new. It rebuilds what a plain `airflow dags trigger` saw on 2.x, since 3.x gives it no date: the latest closed day for billing, and the trigger date for tariffs and the registry.
- **`usage_rollup`:** its interval is rebuilt from the triggering readings runs' intervals, because asset-triggered runs have no interval on 3.x. The per-region row counts now come from the new event names.
- **Templates and helpers:** `sync_tariffs.sh` no longer uses `tomorrow_ds`. `billing_daily` gets `conf` back for the dropbox lookup. `CsvSliceOperator` now uses the new base class and asset objects instead of URI strings.
- **Registry task rename:** in `meter_registry.py` I renamed the callable to `write_registry_snapshot` so the task variable could match its task id. The task id itself is unchanged.
- **Requirements:** `requirements.txt` is now pinned to `apache-airflow==3.3.2` plus `apache-airflow-providers-standard==1.19.0`.

For production, the 3.x deployment needs `plugins/` on both the DAG processor and the workers, as before. `[metering] invoice_dropbox` is still read from `AIRFLOW__METERING__INVOICE_DROPBOX`.