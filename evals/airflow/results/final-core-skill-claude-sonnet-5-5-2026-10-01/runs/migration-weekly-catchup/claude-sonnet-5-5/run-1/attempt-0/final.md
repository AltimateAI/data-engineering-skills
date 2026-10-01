Both DAGs are ported to Airflow 3.3.2 and import cleanly. The Monday report fires on the same dates as before and writes the same weekly CSV and manifest paths. The BEFORE/AFTER output replay could not confirm identical outputs, and the on-call page was never fired.

**Changes**
- **Weekly report:** I replaced the bare cron string with `CronDataIntervalTimetable("0 6 * * 1")`. On 3.x a bare cron string would have shifted every report by a week. `next_ds` is gone in 3.x, so the task now derives week end from `data_interval_end`. I set `multiple_outputs=True` explicitly to keep the old return behaviour.
- **Season re-runs:** the DAG had no `catchup` setting, which meant catch-up was on in 2.x. 3.x defaults to off, so I set `catchup=True` explicitly. A season re-run still produces a report for every week since `start_date`.
- **On-call page:** `sla=` and `sla_miss_callback` are silently ignored in 3.x. I replaced them with a DAG-level `DeadlineAlert` of 3 hours after the run is queued, which calls `notify_growth_oncall`. The callback signature changed to `(context=None, **kwargs)`.
- **`campaign_sync`:** I switched to `schedule=CronDataIntervalTimetable("0 * * * *")` and kept `catchup=False`.
- **Imports and pin:** both DAGs now import from `airflow.sdk`, and `requirements.txt` pins `apache-airflow==3.3.2`.

**Verified**
- The checker reports 0 errors and `ruff --select AIR` is clean.
- A preview of the first five run dates for each DAG matches the 2.x scheduler's, run on a copy of the original DAGs adjusted only enough to import on 3.x.
- Three replayed weekly runs (weeks of Jan 5, 12 and 19) produced `weekly/<week_start>.csv` and `manifests/<week_start>.json` with correct week ranges.

**Not verified**
- **Replay:** no 2.x environment was available, and the old code can't run on 3.3, so there is no baseline to diff the outputs against. The replay harness also flags the runs as errors because Airflow 3.3.2 has a bug with deadline alerts (`'dict' object has no attribute 'hex'`). The tasks themselves ran and wrote the files.
- **On-call page:** the deadline callback was not fired. It is also untested whether the deadline attaches in a real scheduler. In the replay the deadline was skipped because `queued_at` was `None`, which may be a replay artifact.
- **Manual triggers:** the README doesn't describe any for the weekly report. A manually triggered run has no `data_interval_end` in 3.x, so the task would fail. I didn't add handling for that. Tell me if the growth team triggers it by hand and I'll add a fallback.
- **Tests:** the repo has no tests.

The changes are uncommitted in the working tree.