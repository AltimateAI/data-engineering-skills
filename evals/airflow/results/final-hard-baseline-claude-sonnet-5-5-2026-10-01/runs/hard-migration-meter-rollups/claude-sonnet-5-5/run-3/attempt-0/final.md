The project is migrated to Airflow 3.3.2 and parses cleanly. I ran it end to end on 3.3.2, but only compared the outputs against the README's rules, because there is no 2.11 environment here to diff against. I haven't committed anything.

**What I ran**
- I used a copy of the project with the sample data and start dates shifted to recent dates, so catchup produced real runs.
- Scheduled readings loads and the asset-triggered rollups wrote their CSV and manifest files.
- Scheduled billing billed the right day and published `INV-20260930.csv`.
- The registry export wrote the correct file and `as_of`.
- Manual `airflow dags trigger billing_daily` re-billed and re-published the latest closed day.
- Manual `airflow dags trigger tariffs_daily` synced today's and tomorrow's tariffs.
- `usage_rollup` ran only as one-hour windows, because the loads arrived one at a time. I did not test several loads batched into one run.
- Not run: the `tariffs_daily` catchup (it works on the real March start date, but the real tariff file only covers March, so later days would fail), and the registry export on a manual trigger.

**Behaviour changes in 3.3 that I had to counter**
- **Schedules:** Airflow 3 turns cron strings into trigger-style schedules with no data interval, so billing would have billed the wrong day. I pinned all schedules to the interval-based timetable in the new `plugins/meter_lib/timing.py`.
- **Manual runs:** a plain `dags trigger` now has no logical date or data interval, which breaks `billing_daily`, `tariffs_daily` and `{{ ds }}`. The tasks now derive them from the trigger time as 2.x did:
  - `billing_daily` bills the latest closed day.
  - `tariffs_daily` syncs today and tomorrow.
- **`tariffs_daily` catchup:** it relied on the 2.x default of `catchup=True`, which became `False` in 3, so I set it explicitly.
- **`usage_rollup` window:** asset-triggered runs no longer carry a data interval. Each readings load now records its interval in its asset event, and the rollup takes the earliest start and latest end across all triggering events. The README says a rollup spans from the earliest triggering load's start to the latest one's end. Row counts are still summed over every event in the batch.
- **Templates:** `conf` and `tomorrow_ds` no longer exist. I added `invoice_dropbox` and `sync_day` as plugin macros, and `sync_tariffs.sh` now takes its days from environment variables. `[metering] invoice_dropbox` and `AIRFLOW__METERING__INVOICE_DROPBOX` still work.
- **Renames:** `Dataset` became `Asset`, and the imports moved to `airflow.sdk` and the standard provider. `schedule_interval`, `provide_context`, `execution_date` and `default_var` were replaced.
- **Requirements:** `requirements.txt` now pins Airflow 3.3.2 and the standard provider.

**Before cutover**
- The first run of `usage_rollup` after cutover needs readings events created by the new code. Events already queued from 2.11 lack the interval field and would fail the rollup.
- The README has a short Airflow 3 notes section.

I also noticed two existing quirks and left them alone to keep behaviour identical. `sync_tariffs.sh` fails for any day missing from `data/tariffs.csv`, and a manual readings trigger with an explicit logical date uses the interval ending at the current hour, not the date you passed.