The `inventory_snapshot` DAG now runs on Airflow 3.3.2. In my test runs it wrote snapshot CSVs and audit JSON files byte-identical to the 2.x baseline. One caveat: there's no Airflow 2 environment here, so that baseline is the original code run with the dates Airflow 2.11 would have passed it, not a real 2.x run. I changed `dags/inventory_snapshot.py` and `requirements.txt`; nothing is committed yet.

**What would have broken or silently changed on 3.3:**
- **Snapshot dates would shift by a day.** On 3.x a plain `timedelta(days=1)` schedule means the run on day D processes day D, not D−1. I set the schedule to `DeltaDataIntervalTimetable(timedelta(days=1))`, which keeps the 2.x behaviour: the run firing at D+1 00:00 UTC snapshots day D.
- **Both tasks would fail.** `execution_date` and `prev_ds` no longer exist in 3.x. Both tasks now get the date from `logical_date`. "Previous day" is worked out as before: the day before for scheduled runs, and the run's own date for a manual trigger, which is what 2.x did.
- **The audit JSON would have had nulls.** On 3.x, fetching a value from the earlier task without naming it returns nothing, so `sku_count` and `low_stock` would have been `null`. The audit task now names `build_snapshot` explicitly.
- **Manual triggers would fail.** A manual run on 3.x has no logical date. The DAG now falls back to the trigger time, which matches what 2.x used.
- **Other updates:**
  - removed `provide_context`, which 3.x rejects
  - moved imports to the `airflow.sdk` and standard-provider paths
  - made the start date explicitly UTC
  - renamed the task functions to `_build_snapshot` / `_audit_snapshot` so the task variables can match their task IDs; task IDs and dependencies are unchanged
- **Unchanged:** `catchup=False`, output paths, file names, CSV and JSON formats.
- **Requirements:** pinned `apache-airflow==3.3.2` and added `apache-airflow-providers-standard==1.19.0` (the version installed in your venv).

**How it was checked:**
- **Run dates:** the next 5 scheduled runs on 3.3.2 have the same fire times, logical dates and date windows as under 2.x defaults.
- **Lint and import:** Airflow's upgrade checks and the full ruff Airflow ruleset pass, and the DAG loads with no import errors.
- **Outputs:** I ran 8 consecutive scheduled runs (2026-02-20 to 02-27) and one manual trigger at 2026-03-03 09:15 UTC through Airflow 3.3.2. For the baseline, I called the original, unmodified task functions directly with the values 2.11 would have given them. All 18 files were byte-identical.

**Not verified:**
- I couldn't run Airflow 2.11 itself, since only 3.3.2 is installed.
- The repo has no test suite, so no tests were run.
- I didn't check whether your old cluster overrode the default timezone; I assumed UTC, which is the default.
- I only tested a manual trigger with no `--conf`.

One existing quirk is kept as-is: a manual run snapshots stock up to 24 hours after the trigger time, and computes `change` against that day's existing snapshot if there is one. That's how 2.x behaved too, so the outputs match, but it may not be what the replenishment team expects from a manual run.