Both DAGs now parse on Airflow 3.3.2 with no import errors, and the report's scheduling behaves as the README describes. I haven't executed any tasks or triggered a real run. I haven't confirmed that the on-call page fires, and that callback only prints a message, as it did before.

I checked that `weekly_campaign_report` schedules its first run for the interval Mon 2026‑01‑05 06:00 → Mon 2026‑01‑12 06:00, so the catch-up generates one run per week.

**`dags/weekly_campaign_report.py`**
- **Schedule:** Airflow 3 turns a plain cron string into a point-in-time trigger, which would change what "the previous Mon–Sun week" means. I used `CronDataIntervalTimetable("0 6 * * 1", timezone="UTC")` to keep the same weekly interval and the same `output/weekly/<week_start>.csv` names.
- **Season re-runs:** Airflow 3 defaults `catchup` to False, so I set `catchup=True` explicitly. Without it, setting `start_date` to the season's first Monday would have produced a single run instead of one per week.
- **Task dates:** `next_ds` no longer exists in Airflow 3. `summarize_week` now builds its dates from `data_interval_start` and `data_interval_end`.
- **On-call page:** SLAs and `sla_miss_callback` were removed in Airflow 3. I replaced them with a `DeadlineAlert` of 3 hours from when the run is queued, which calls `notify_growth_oncall`. That function now takes the new callback arguments.
- **Imports:** `airflow.decorators` became `airflow.sdk`.

**`dags/campaign_sync.py`**
- `schedule_interval` became `schedule`, and the import moved to `airflow.sdk`. It already had `catchup=False`.

**`requirements.txt`**
- `apache-airflow` is pinned to 3.3.2.

**Check before relying on it**
- **SLA timing:** the old SLA was measured from the scheduled end of the interval (Monday 06:00), while the new deadline counts from when the run is queued. For the normal weekly run these are the same. During a season re-run, an old SLA would have fired for every backfilled week at once. The new deadline fires only if a run takes more than 3 hours, which I think is the better behaviour, but say if you want the old one.
- **Callback:** `notify_growth_oncall` only prints, as before. If it is supposed to reach a pager, the README says it pages the on-call analyst, but nothing in this repo does that.