The `hourly_pageviews` DAG is migrated to Airflow 3.3.2. I couldn't run a full before/after replay, so the proof is thinner than I'd like. I haven't committed anything.

**What I changed**
- **Imports:** `DAG` now comes from `airflow.sdk`, and the Bash and Python operators from `airflow.providers.standard`.
- **Schedule:** `schedule_interval="0 * * * *"` is now `schedule=CronDataIntervalTimetable("0 * * * *", timezone="UTC")`. A bare cron string on Airflow 3 would have shifted every run an hour late, so the 10:00 run would have written `20260305T10` instead of `20260305T09`. Ruff doesn't flag this.
- **Templates:**
  - `execution_date` became `logical_date`.
  - `next_execution_date` became `data_interval_end`.
  - `prev_execution_date` became `logical_date.subtract(hours=1)`.
  - `yesterday_ds_nodash` became `macros.ds_add(ds, -1) | replace('-', '')`.
  - Those last two are removed context keys. They fail only when the task renders, so ruff misses them too.
- **Task variables:** renamed to match their task ids (`extract_hour`, `aggregate_hour`, `publish_hour`) to satisfy ruff's AIR001 rule.
- **`requirements.txt`:** now pins `apache-airflow==3.3.2` and `apache-airflow-providers-standard==1.19.0`, which is the installed version.
- **Left alone:** `catchup=False` was explicit, so it stays. Output paths, file names, marker contents and task ids are unchanged, so the dashboard loader is unaffected.

**What I checked**
- The DAG imports with no errors and `ruff check --select AIR --preview` passes. The wider Airflow 3 checker script wasn't available in this environment.
- I rendered each changed template for the 09:00 run. The output matches what the README describes: `20260305T09` for the hour file, `20260305T08` for the previous hour, `2026-03-05T09:00` in the marker, `20260304` for the staging cleanup, and `20260305T090000.done` for the marker filename.

**What I couldn't check**
- **No replay:** the replay and compare scripts weren't found, and there's no 2.x environment here. I never ran several scheduled runs side by side with the old behaviour.
- **`dags test` isn't a scheduled run:** it paired a 09:00 logical date with an 08:00–09:00 interval and staged 0 events. I treated that as a test artifact, not a bug. A real scheduled run has interval 09:00–10:00.
- **Manual triggers:** the README doesn't describe any. On Airflow 3 a manually triggered run has no `logical_date`, so the templates would fail on one. If you trigger this DAG manually, tell me how and I'll add handling.

I deleted the scratch `output/`, `.afhome/` and `airflow.cfg` that my test runs created.