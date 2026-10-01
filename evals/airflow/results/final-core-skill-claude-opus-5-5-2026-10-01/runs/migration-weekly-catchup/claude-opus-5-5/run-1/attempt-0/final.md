Both marketing DAGs now run on Airflow 3.3.2. The weekly report covers the same weeks, writes the same files and catches up for season re-runs, and the late-report page is rebuilt on Airflow 3's replacement for SLAs. I couldn't fire the page in a test, and the only exact baseline was a by-hand recompute from the CSV (details below). The changes are uncommitted.

**Problems I fixed in `weekly_campaign_report`**

A plain rename to 3.3 would have broken four things, none of which shows up as an error when the DAG loads:

1. **Season re-runs would have stopped.** The DAG had no `catchup` setting. On 2.x that meant "one run per week since `start_date`"; on 3.x it means "only the latest week". I set `catchup=True` explicitly.
2. **Reports would have shifted by one week.** On 3.x the bare cron `"0 6 * * 1"` would make Monday's run report the week starting that day, not the Mon–Sun week that just ended. I switched to the timetable that keeps 2.x's behaviour (`CronDataIntervalTimetable`), so each Monday run still covers the previous week.
3. **`next_ds` no longer exists in 3.x**, so the task would have crashed. The week bounds now come from the run's start and end dates, and files are still named `<week_start>`.
4. **The on-call page would have gone silent.** 3.x accepts `sla=` and `sla_miss_callback` but ignores them. I replaced them with a deadline alert that calls `notify_growth_oncall` if the run isn't finished 3h after it's queued. That is the "finished by 09:00 for a 06:00 start" rule.

**Other changes**
- **Manual triggers:** on 3.x these have no dates, so the original code would crash. They now report the latest finished Mon–Sun week. On 2.x a manual trigger would have written an empty report named after the trigger day. The README doesn't describe manual runs, so this changes nothing the growth team relies on, but it is a change.
- **`campaign_sync`:** imports updated and the same timetable switch so the hourly run times stay identical; `catchup=False` stays as it was.
- **`requirements.txt`:** now `apache-airflow==3.3.2`.

**Verification**
- Airflow's static checks pass on both DAGs, and the next 5 scheduled runs of each have the same dates on 3.3 as under 2.x.
- I replayed 3 hourly sync runs, 4 consecutive Monday runs and a manual trigger. All succeeded, and the hourly sync output matches the original.
- There's no 2.x environment here, and the original weekly code can't run on 3.x, so I had no direct "before" output. Instead I recomputed each week's per-campaign totals straight from `campaign_events.csv`; all 5 weekly CSVs match exactly. The manifests have the right week start and end.

**Not verified**
- **The on-call page has not been fired.** On 3.3.2, `airflow dags test` fails with `'dict' object has no attribute 'hex'` on any DAG with a deadline alert, after all tasks have already succeeded. It's an Airflow bug, not ours. I checked the report output on a copy with the deadline removed. It's worth confirming the page actually triggers on the real scheduler.
- **Expect a backlog when the DAG is unpaused.** With catchup on and `start_date` of 2026-01-05, about 38 weekly runs will queue (2 at a time). That's what 2.x would have done too, and it's what season re-runs need. Each backfilled run counts 3h from when it's queued, so it should only page if it actually runs late.

There are no tests in the repo, so there was no test suite to update.