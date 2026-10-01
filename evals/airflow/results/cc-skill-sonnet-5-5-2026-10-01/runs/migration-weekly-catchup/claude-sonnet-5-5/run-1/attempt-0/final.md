Both marketing DAGs are ported to Airflow 3.3.2. The checker and a before/after schedule comparison pass. The runtime test is only partly clean (details below), and nothing is committed.

**Changes**
- **`weekly_campaign_report`:**
  - I swapped the bare cron string for `CronDataIntervalTimetable("0 6 * * 1", timezone="UTC")`. On 3.x a bare cron would have shifted every report by a week. The report still covers the previous Mon–Sun week and writes the same `output/weekly/<week_start>.csv` and manifest.
  - `catchup=True` is now explicit. The DAG never set it, and 2.x defaulted to True. On 3.x the default is False, so without this the season re-runs from an earlier `start_date` would silently stop producing a run per week.
  - `next_ds` no longer exists in 3.x, so the task now takes the week end from `data_interval_end`.
  - The SLA is rebuilt as a DAG deadline of 3h after the run is queued, which pages at 09:00 UTC. `sla` and `sla_miss_callback` are removed, because 3.x accepts them but ignores them and the page would have stopped. `notify_growth_oncall` now takes `(context=None, **kwargs)`.
- **`campaign_sync`:** hourly, now a cron-interval timetable. `catchup=False` is kept.
- **`requirements.txt`:** now pins `apache-airflow==3.3.2`. I didn't add `apache-airflow-providers-standard` because nothing imports it.
- **Imports:** `airflow.decorators` became `airflow.sdk`.

**Verified**
- The checker reports 0 errors and 0 import errors, and `ruff --select AIR` is clean.
- I captured the schedule preview with 2.x scheduler defaults before editing and compared it after. Run times, logical dates and data intervals match for both DAGs. The weekly report is still 06:00 UTC on Mondays, with the first run on 2026-01-12 covering 01-05 to 01-12.
- `airflow dags test` ran every task successfully for both DAGs.

**Not verified**
- **Deadline alert:** I didn't confirm the deadline fires or that the callback pages anyone. `airflow dags test` on the weekly DAG also ended with `AttributeError: 'dict' object has no attribute 'hex'` after its tasks succeeded. That's a known Airflow 3.3.2 bug when a DAG has a deadline alert, so I kept the deadline.
- **Weekly period:** `dags test` runs manual-style, so it didn't exercise the real weekly period. Its output had the wrong week and no campaigns. The preview comparison is what confirms the real schedule.
- **Season backfill:** I didn't test the season re-run end to end.
- **Project tests:** the repo has none.

**Before you unpause:** `catchup=True` with `start_date` 2026-01-05 will create about 38 weekly runs, which is the same as on 2.x. `max_active_runs=2` limits how many run at once.

I removed the generated `output/` files and my scratch directory.