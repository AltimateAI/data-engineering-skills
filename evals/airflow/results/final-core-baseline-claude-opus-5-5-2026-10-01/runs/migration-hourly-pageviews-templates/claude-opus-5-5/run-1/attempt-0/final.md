The `hourly_pageviews` DAG now works on Airflow 3.3.2. The hourly CSVs and the `.done` markers keep the same names and contents the README describes. I tested it with real `airflow dags test` runs on the sample data, and the changes aren't committed.

**What ruff's rules miss:**

1. **The schedule.** In Airflow 3, with your config's `create_cron_data_intervals = False`, a plain `"0 * * * *"` gives a different kind of schedule. The 10:00 run would get logical date 10:00 and an empty time window (10:00–10:00). So you'd get a file named `T10` with zero events, not `20260305T09.csv` with the 09:00–10:00 data. I set the schedule to `CronDataIntervalTimetable("0 * * * *", timezone="UTC")`, which restores the Airflow 2 hourly windows whatever that config says.
2. **Template variables removed in Airflow 3**, replaced like this:
   - `execution_date` / `next_execution_date` → `data_interval_start` / `data_interval_end`
   - `prev_execution_date` → `data_interval_start` minus 1 hour
   - `yesterday_ds_nodash` → `data_interval_start` minus 1 day
3. **The marker name.** I build it from `data_interval_start` instead of `ts_nodash`. For manual runs in Airflow 3, the logical date can differ from the start of the hour being processed. With `ts_nodash`, a manual run at 10:00 would write `T100000.done` next to `T09.csv`.
4. **What ruff did catch:** `schedule_interval` → `schedule`, and the new import paths (`airflow.sdk.DAG` and the standard-provider operators). I also bumped `requirements.txt` to 3.3.2. The only remaining ruff warnings are optional style checks about task variable names.

**Test results:**
- The run covering 09:00–10:00 wrote `20260305T09.csv` and `20260305T090000.done` containing `hour=2026-03-05T09:00 staged=53`.
- The change from the previous hour was filled in, and the first hour with data left it blank, as before.
- The run for midnight on 2026-03-06 deleted the 2026-03-05 staging files.
- I deleted the test output afterwards.

**Manual triggers:** In Airflow 3 you can trigger a run without a logical date. That run has no time window, so its tasks will fail instead of guessing which hour to process. Scheduled runs and manual runs given a logical date are unaffected. To re-run a specific hour, trigger with a logical date or clear the scheduled run.