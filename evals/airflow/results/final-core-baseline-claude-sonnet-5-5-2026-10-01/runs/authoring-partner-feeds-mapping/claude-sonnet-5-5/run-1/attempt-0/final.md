I added the `partner_feeds` DAG in `dags/partner_feeds.py`. I ran it with `airflow dags test` on 2026-09-03 (four files) and 2026-09-05 (no folder), and both produced the expected outputs.

- **Files per day:** a `list_partners` task lists the `*.csv` files in `data/partner_drop/<ds>/`. If the folder doesn't exist it returns an empty list, so new or missing partners need no config.
- **One task per file:** `process_file` is mapped over that list, so each file is its own task instance. A broken file fails and retries (2 retries) on its own, and the other files finish normally. It writes `output/partner_feeds/<ds>/<partner>.json`.
- **Summary:** `write_summary` writes `summary.json` once the mapped tasks finish. It uses `trigger_rule="none_failed"`. With the default rule, a day with no files would skip the summary, because the mapped task gets skipped. If any file fails, the summary doesn't run, so finance never gets a partial total.
- **Rerunning dates:** `start_date` is 2026-09-01 and `catchup=True`, so any date since then can be cleared or backfilled. Output files are overwritten atomically on each run.
- **Amounts:** they are summed as decimals and rounded to 2 dp, so there's no float drift.

Test results:
- **2026-09-03:** acme has 25 rows totalling 7502.67, and the summary is `{"files": 4, "rows": 50, "total_amount": 14467.21}`.
- **2026-09-05:** the summary is `{"files": 0, "rows": 0, "total_amount": 0.0}`.

`catchup=True` will create a run for every day since 2026-09-01 as soon as the DAG is unpaused. I capped it at `max_active_runs=4`. Switch it to `False` if you'd rather trigger dates by hand.

I used a throwaway Airflow home for the tests and removed it. `output/` is gitignored, so the test outputs aren't in the git status.