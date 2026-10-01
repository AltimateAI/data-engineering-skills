Both DAGs now parse cleanly under Airflow 3.3.2 with no import errors. I haven't run the DAGs themselves, so the week-by-week output, the season re-runs and the page are untested.

**What changed**
- **Imports:** `airflow.decorators` becomes `airflow.sdk` in both DAGs, and `schedule_interval` becomes `schedule`.
- **`requirements.txt`:** now pins `apache-airflow==3.3.2`.
- **Season re-runs:** Airflow 3 defaults `catchup` to off. `weekly_campaign_report` now sets `catchup=True`, so a `start_date` on the season's first Monday gives one run per week again. `campaign_sync` already had `catchup=False`, so it is unchanged.
- **Week boundaries:** Airflow 3 turns a cron string into a trigger-style schedule with no Monday-to-Sunday interval, which would have changed which week gets reported. The DAG now uses `CronDataIntervalTimetable("0 6 * * 1", timezone="UTC")`, which keeps the old interval.
- **Templates:** `next_ds` no longer exists. The task now builds `ds` and `next_ds` from `logical_date` and `data_interval_end`, so the output files and manifests keep the same names (`<week_start>.csv` and `<week_start>.json`).
- **On-call page:** Airflow 3 removed `sla` and `sla_miss_callback`, so the old page would have silently stopped. I replaced it with a `DeadlineAlert` that calls `notify_growth_oncall` 7 days and 3 hours after the logical date. That is 09:00 UTC Monday, the same 3 hours after start the SLA used.

**Before this goes live**
- **Placeholder page:** `notify_growth_oncall` still only prints, as it did before. If the on-call page is actually delivered some other way, that hook needs wiring up. Its signature changed to take the run context.
- **Season re-run pages:** for old weeks, the deadline has already passed when those runs are created, so a season re-run will probably page once per back-filled week. The old SLA did the same. If that is too noisy, I can change the deadline to count from when the run is queued, but runs waiting behind `max_active_runs=2` would then count as late. Say if you want it.