The project now runs on Airflow 3.3.2, and on my replay every scheduled run and the manual re-close wrote exactly the same files as 2.11, audit records included.

**How I checked:** I ran the original code on the local 2.11 venv and the migrated code on 3.3.2 over the same timeline, 2026-03-01 to 2026-03-17. That covered all six DAGs: 469 scheduled runs plus four `airflow dags trigger daily_close` re-closes (Monday morning, Wednesday, Sunday, late Monday). All 473 runs succeeded on both. The 507 output files are byte-identical, and I also hashed the whole output folder after every run, so the matches hold run by run, not just at the end.

One limit on that test: it drove runs through Airflow's built-in test runner, not a live scheduler. I created each run with the type and dates the scheduler would give it. The DAGs that don't catch up were replayed as if the scheduler had been running continuously since their start date.

**What I changed and why:**
- **Schedules:** 3.3 schedules cron strings and `timedelta`s differently by default, which changes `ds` and the date ranges each run covers. I pinned them to the 2.11 behaviour. `vendor_payments` stays on New York time.
- **Plain `airflow dags trigger daily_close`:** in 3.3 this creates a run with no logical date and no date range, so the re-close would fail. It now works out the business day from the trigger time, the same way 2.11 did. The fix is in `plugins/ledger_lib/workdays.py`, used by both `daily_close` tasks.
- **Audit record (`started_by`):** `dag_run.external_trigger` no longer exists. It's now based on the run type, so CLI/UI/API runs and runs started by `TriggerDagRunOperator` still record `"operator"`.
- **Hourly extract:** 3.3 changed how `xcom_pull(..., include_prior_dates=True)` behaves, so the extract got back a list of every earlier high-water mark instead of the latest one. I added `map_indexes=-1`. I confirmed this one matters: with the change reverted, the extract crashes on its third run.
- **Removed template variables:**
  - In `fx_revaluation.sql`, `next_ds` is replaced with `data_interval_end | ds` and `yesterday_ds` with `macros.ds_add(ds, -1)`.
  - `conf.get('ledger', 'base_currency')` is now a new `macros.ledger.base_currency()` macro.
  - The weekly report computes `prev_ds` itself.
- **Imports:** moved to `airflow.sdk`, and `BashOperator` now comes from the standard provider. `requirements.txt` now pins `apache-airflow==3.3.2` and adds `apache-airflow-providers-standard`, and I updated the README a little.

**Things to know before the cutover:**
- Run IDs for scheduled runs now end in the time the run is due rather than its logical date (e.g. `scheduled__2026-03-17T12:00:00`). This doesn't change any output file.
- A plain trigger with no logical date only works for `daily_close`, which is the runbook case. The other DAGs would need `-l <date>`, and even then their dates wouldn't match a 2.11 manual run. Their manual runs weren't in scope, so I didn't try to make them match.
- `airflow dags trigger` still works in 3.3 but is marked deprecated in favour of `airflowctl dags trigger`.

Nothing is committed. The harness and both output trees are in `../tmp/` if the auditors want to re-run the comparison.