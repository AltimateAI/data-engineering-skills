I fixed both failures in `dags/partner_feed.py`. I ran the dated path through `airflow dags test`. I could only check the no-date path with a stand-in object, not a real date-less trigger.

**Causes**
- **`KeyError: 'execution_date'`:** Airflow 3 removed that context key. `write_manifest` read it.
- **`KeyError: 'logical_date'`:** a manual trigger with an empty date has no `logical_date` on Airflow 3, so `extract_orders` had nothing to read. `deliver` would have failed next, because `{{ ds_nodash }}` is also undefined on those runs.
- **Hidden shift in the schedule:** `"0 4 * * *"` as a bare string is now a trigger timetable. Fixing only the two errors would have shifted every scheduled feed forward by a day.

**Changes**
- **Schedule:** it is now `CronDataIntervalTimetable("0 4 * * *", timezone="UTC")`. The run at 04:00 on D+1 still has logical date D and produces day D's feed, as before. I made `start_date` timezone-aware (UTC) to match.
- **One `feed_day(dag_run)` helper:** `extract_orders`, `write_manifest` and `deliver` all use it, so the three steps can't disagree on the day. It uses `logical_date` when the run has one. Otherwise it uses `run_after`, converted to UTC.
- **Clear and re-run:** a run's `run_after` is fixed when the run is created. Clearing it tomorrow therefore still produces the original day's feed.
- **Unchanged:** the task ids, the extract → manifest → deliver order, and the output and outbox file names (`acme_orders_YYYYMMDD.csv` and `.manifest.json`).

**Checks**
- I ran `airflow dags test` for the 2026-03-03 04:00 tick against a throwaway database. All three tasks succeeded and wrote the 2026-03-03 files. The manifest shows 6 rows, matching the 6 acme rows for that date in the CSV.
- That test passed an explicit date, so it exercised the logical-date path only. The no-date path was checked on `feed_day` directly with a stand-in object. With no logical date and a `run_after` of 2026-03-05 23:30 New York time, it returned `2026-03-06`, the UTC date.
- The skill's `airflow_check.py` and `manual_run.py` scripts weren't on this machine, so I skipped the before/after schedule comparison and the no-date `manual_run` check. Do one real UI trigger with an empty date before relying on it.

I deleted the test output and the temporary Airflow files, so the working tree only has the change to `partner_feed.py`. `partner_catalog_sync.py` uses neither removed key nor date logic, so I left it alone. It still has a bare cron string and so runs at a different time than on 2.x, but only the date-based `partner_feed` output was affected.