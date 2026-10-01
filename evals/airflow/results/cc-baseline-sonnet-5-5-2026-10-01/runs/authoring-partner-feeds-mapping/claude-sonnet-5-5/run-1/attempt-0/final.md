I added the `partner_feeds` DAG in `dags/partner_feeds.py`. I ran it with `airflow dags test` for 2026-09-03 and 2026-09-05, and both runs finished successfully with the expected files. I didn't test a failing or retrying file.

- **Discovery:** `list_partners` globs `data/partner_drop/<ds>/*.csv` and returns the partner names. It returns an empty list if the date folder doesn't exist, so a new partner needs no code change.
- **Per-file work:** `process_file` is a mapped task with one instance per file. It writes `output/partner_feeds/<ds>/<partner>.json` with `partner`, `rows` and `total_amount`. A broken file fails and retries only its own instance. Amounts are summed as decimals and rounded to 2 dp.
- **Summary:** `summarize` writes `summary.json` with `files`, `rows` and `total_amount`. It runs even when there are no files, so empty days get all zeros. It still won't run if any file task failed, so finance never sees a summary that is missing a file.
- **Writes:** Each JSON file is written to a temporary file and then renamed, so a rerun never leaves a half-written file.
- **Reruns:** The schedule is `@daily` with `start_date=2026-09-01` and `catchup=True`. You can backfill or clear and rerun any date since then, and the outputs are overwritten each time.

On 2026-09-03 the summary was 4 files, 50 rows and 14467.21. On 2026-09-05, which has no folder, it was 0 files, 0 rows and 0.0.

I removed the test outputs and the temporary Airflow setup afterwards, so the working tree contains only the new DAG file.