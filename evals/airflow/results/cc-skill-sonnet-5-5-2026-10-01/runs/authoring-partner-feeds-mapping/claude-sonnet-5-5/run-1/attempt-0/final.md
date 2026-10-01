I added the `partner_feeds` DAG in `dags/partner_feeds.py`. Run through `airflow dags test` on Airflow 3.3.2, it wrote the expected outputs for 2026-09-03, 2026-09-04 and an empty day (2026-09-05).

**How it works**
- **Schedule:** the daily run for date D fires at midnight after D ends, so the files have arrived. The run's date is D. Manual runs with no logical date fall back to the trigger time (UTC).
- **`list_partners`:** lists `data/partner_drop/<date>/*.csv`. A missing folder gives an empty list. It also deletes old `<partner>.json` files for that date that no longer have a CSV, so a rerun doesn't leave stale output.
- **`process_file`:** one task instance per file, with 2 retries. It writes `output/partner_feeds/<date>/<partner>.json`, summing amounts with `Decimal`. Output is written to a temp file and then renamed, so a retry or rerun replaces it cleanly.
- **`summarize`:** writes `summary.json` with the file count, row total and amount total. It runs even when no files were processed, so a no-file day gets `{"files": 0, "rows": 0, "total_amount": 0.0}`.
- **Reruns:** `start_date` is 2026-09-01 and `catchup` is off. To rerun a date, clear its run or use `airflow backfill create`. All writes are overwrites.

**Verified**
- `airflow dags test` on 2026-09-03 (4 files, summary 50 rows / 14467.21) and 2026-09-04 (2 files, 15 rows / 3989.83).
- On 2026-09-05 (no folder), the summary was all zeros.
- A repeat of 2026-09-03 gave the same output.
- The DAG has no import errors.

**Not verified**
- Skill scripts: I didn't run the skill's `airflow_check.py` or `manual_run.py`.
- Manual run with an empty logical date: only the `logical_date` path was exercised.
- Failure and retry of a broken file: only the success path was exercised.

I deleted the test outputs and the stray `airflow.cfg` it created, so only `dags/partner_feeds.py` is new in the working tree.