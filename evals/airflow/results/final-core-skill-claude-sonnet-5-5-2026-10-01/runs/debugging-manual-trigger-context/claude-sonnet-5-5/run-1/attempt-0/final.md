I fixed `partner_feed` in `dags/partner_feed.py`. I couldn't replay on Airflow 2, so "same as before" for scheduled runs rests on the schedule preview, not a before/after diff. The DAG's `schedule`, `start_date` and `catchup=False` are unchanged. `partner_catalog_sync` doesn't use dates, so I left it alone.

I ran the DAG in-process on 3.3.2: two scheduled runs and one manual trigger with no logical date. All three tasks succeeded each time.

**Causes**
- **`KeyError: 'execution_date'`** (scheduled run, `write_manifest`): Airflow 3 removed that context key.
- **`KeyError: 'logical_date'`** (UI trigger, `extract_orders`): in Airflow 3 a manual run with an empty date has no `logical_date` at all. Only `dag_run.run_after` (the trigger time) is set.
- **A second break behind the first, in `deliver`:** its `{{ ds_nodash }}` is also undefined on a manual run. It would have failed next if the first error were fixed alone.
- **Silent date shift:** a bare `"0 4 * * *"` string now makes each run's logical date the moment it fires. Under 2.x it was the start of the day-long window that had just closed. A plain rename of `execution_date` would have shifted every feed by a day.

**Changes**
- **Schedule:** `schedule` is now `CronDataIntervalTimetable("0 4 * * *", timezone="UTC")`, which keeps the 2.x dates. The preview shows the 04:00 run on 03-02 with logical date 03-01, as on 2.x.
- **Feed day:** one helper, `feed_day(dag_run)`, picks `dag_run.logical_date`, or `dag_run.run_after` when there isn't one, and formats it in UTC.
- **Clear and re-run:** `run_after` is set once per run and doesn't change, so clearing a manual run tomorrow rebuilds the same day's feed. I didn't test a clear in a live Airflow.
- **Tasks:** `extract_orders` and `write_manifest` use that helper, and `deliver` builds its date from the same expression.
- **Unchanged:** the file names (`output/partner_feed/<day>/orders.csv`, `manifest.json`, `outbox/acme/acme_orders_<YYYYMMDD>.csv` and `.manifest.json`) and the extract → manifest → deliver chain.

**Checks**
- **Static checker:** `airflow_check.py` exits 0.
- **Scheduled runs:** logical dates 03-01 and 03-02 wrote 2026-03-01 and 2026-03-02 files.
- **Manual trigger:** a run triggered at 2026-03-05T23:50Z with no logical date wrote 2026-03-05 files in both `output` and `outbox`.

I deleted the `output/` and `outbox/` files the test runs created. I didn't commit anything.