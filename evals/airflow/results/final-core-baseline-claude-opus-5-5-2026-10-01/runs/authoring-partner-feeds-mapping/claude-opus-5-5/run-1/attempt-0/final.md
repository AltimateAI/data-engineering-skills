I've added the `partner_feeds` DAG in `dags/partner_feeds.py`. I ran it locally with `airflow dags test` and it handled normal days, no-file days, broken files and reruns correctly.

**How it works**
1. **`list_files`** finds the `*.csv` files in `data/partner_drop/<ds>/`. If the folder doesn't exist, it returns an empty list.
2. **`process_file`** runs once per file as its own task instance, labelled by partner name in the UI. It writes `<partner>.json` with the row count and the amount total to 2 decimal places. A missing column or a bad amount fails only that file's task, which retries twice, 5 minutes apart.
3. **`write_summary`** writes `summary.json` once all files have succeeded. On a day with no files, Airflow skips the per-file step; the summary runs anyway (trigger rule `none_failed`) and writes zeros. If a file is still failing, the summary isn't written.

**Test results**
- **2026-09-03 (4 files):** 50 rows totalling 14467.21. The per-partner and overall figures match an independent pandas calculation.
- **2026-09-01 (no folder):** `{"files": 0, "rows": 0, "total_amount": 0.0}`.
- **Broken file** (an `oops` amount, on a scratch date): `globex` and `hooli` finished, `broken` went to retry, and the summary waited.
- **Rerun after removing a partner's file:** that partner's old JSON was deleted and the summary was correct. Each rerun of a date first removes partner outputs that no longer have an input file, so a rerun leaves only current results.

I deleted all test data and outputs afterwards, plus an `airflow.cfg` that my first failed test run created. The only new file is the DAG. Nothing is committed yet.

**Decisions for you to check**
- **When it runs:** the run for date D starts at 00:00 UTC on D+1, after the day's uploads are done, so it reads a complete folder. This differs from `partner_registry_export`, which runs at 01:00 and uses the current day's date. If partners upload the previous business day's files in the morning instead, the schedule needs changing.
- **Reruns:** `start_date` is 2026-09-01 and `catchup=False`, matching your other DAG. Any date can be rerun with `airflow backfill create` or by clearing that day's run, and up to 4 dates can run at once.
- **Totals** are summed exactly and stored as JSON numbers, so a total like 12.50 appears as `12.5`. If finance needs exactly two decimal places in the file, it would have to be stored as a string.