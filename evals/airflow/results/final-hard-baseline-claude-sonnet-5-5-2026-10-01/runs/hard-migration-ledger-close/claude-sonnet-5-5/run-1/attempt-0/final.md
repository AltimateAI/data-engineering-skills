The project now parses and runs on Airflow 3.3.2, and the runs I tested wrote the files I'd expect from 2.11. I couldn't run 2.11 here, so none of this is a byte-for-byte diff against real 2.11 output.

**What I ran on 3.3.2**
- All six DAGs import without errors.
- I ran a real scheduler and API server against `daily_close`. Scheduled catch-up runs for 03-02 to 03-04 wrote the day's net and balances files, and the audit record says `scheduler`.
- `airflow dags trigger daily_close`, the runbook command, re-closed 2026-09-30 when run on Thursday 10-01. That is the latest business day that has ended. The audit record says `operator`. I did not test the Monday-morning case.
- Scheduled runs also produced the weekly report, the FX file, the vendor payments file, the housekeeping count and the hourly batch. The hourly cursor held across two runs: later batches came out empty, so no posting was extracted twice.
- The FX output was empty because `fx_rates.csv` has no rates for the dates the run covered. So the FX SQL rendered and ran, but I haven't compared its numbers.
- I did not run the weekly report or vendor payments across several periods, so their outputs are checked only for file names and the dates in them.

**What I changed and why**
- **Schedules:** Airflow 3 turns cron and `timedelta` strings into point-in-time schedules, which shifts run dates and file names. I replaced every `schedule_interval` with the explicit data-interval timetables 2.x used (`CronDataIntervalTimetable` and `DeltaDataIntervalTimetable`).
- **Manual run:** in 3.x `airflow dags trigger` creates a run with no logical date and no data interval, so `data_interval_start` is missing. A new `plugins/ledger_lib/context.py` works the interval out from the trigger time using the DAG's timetable, as 2.x did. The operator and `roll_balances` both use it.
- **Audit record:** `dag_run.external_trigger` no longer exists, so the operator now checks `run_type == "manual"`.
- **Template variables:** `prev_ds`, `next_ds` and `yesterday_ds` are gone. The weekly DAG and the FX SQL now compute the same values from the data interval.
- **Base currency:** `conf` is no longer available in templates. I added a `macros.ledger.base_currency()` macro that reads `[ledger] base_currency` when the task renders.
- **Imports and dependencies:** imports moved to `airflow.sdk`, and `BashOperator` now comes from the standard provider. `requirements.txt` pins 3.3.2 and adds `apache-airflow-providers-standard`.
- **README:** I added a short note about the manual-trigger behaviour.

**Things to know before cutover**
- Manual runs of the other DAGs (`fx_revaluation_daily`, `close_report_weekly`, `vendor_payments_weekday`, `gl_postings_hourly`) won't match 2.x. A run with no logical date has no `ds`, and the ones that read it will fail. The runbook only covers `daily_close`, so I left them.
- `airflow dags test <dag> <date>` makes a manual run, so it won't reproduce scheduled-run dates.
- To run the scheduler locally I had to set `AIRFLOW__CORE__EXECUTION_API_SERVER_URL` to point at my API server. In production, check that setting is correct.

I deleted the generated `output/` directory. I could not kill my local scheduler and API server because `pkill` was denied for other processes. If they are still running, stop them.