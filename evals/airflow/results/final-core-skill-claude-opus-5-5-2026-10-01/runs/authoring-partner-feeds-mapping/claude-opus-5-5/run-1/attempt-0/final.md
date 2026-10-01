I've added the `partner_feeds` DAG in `dags/partner_feeds.py` (Airflow 3.3.2, per `requirements.txt`). It parses cleanly and wrote correct output for every test day I ran, including a day with no files.

**How it works**
1. `list_partners` lists `data/partner_drop/<day>/*.csv`. If the folder doesn't exist, it returns an empty list instead of failing.
2. `process_file` runs once per file, and each instance is labelled with the partner's name in the UI. It writes `output/partner_feeds/<day>/<partner>.json`. Sums use exact decimal arithmetic, and a file with a bad amount or no `amount` column fails with the line number. Each file has 2 retries, 5 minutes apart, and a failure doesn't stop the other files.
3. `write_summary` writes `summary.json` once every file has succeeded. When there are no files it still runs and writes zeros.

Outputs are fully rewritten on every run, never appended. A rerun also deletes the output of any partner whose file is no longer in the folder, so the summary always matches the files that are actually there.

**Which day each run processes (UTC)**
- **Scheduled run** at 23:30 on day D: processes D.
- **Manual trigger without a date:** processes the day of the trigger.
- **Rerun, clear or backfill of D:** processes D again.
- **Specific day:** you can also trigger with `params.day=YYYY-MM-DD`.

`start_date` is 2026-09-01 with `catchup=False`. To rerun a range, use `airflow backfill create --dag-id partner_feeds --from-date 2026-09-01T00:00:00+00:00 --to-date ...`; it works even though catchup is off.

**What I ran**
- **Static check:** passed, and the upcoming run times are 23:30 UTC daily, each for its own day. The one warning confirms the DAG processes the day it runs, which is what you asked for.
- **Four days, 2026-09-01 to 09-04, plus a manual trigger and a rerun of 09-02:** all 6 runs succeeded.
  - 09-01 (no folder) wrote `{"files":0,"rows":0,"total_amount":0.0}`.
  - The other days matched a separate count I did directly from the CSVs. For example, 09-03 came out as 4 files, 50 rows, 14467.21.
  - The rerun gave identical output.
- **Broken-file test:** I made a temporary day with a good file and a bad one, using a copy of the DAG with a 1-second retry delay. The bad file was tried 3 times and failed; the good file succeeded on the first try, and the summary was held back. After I removed the bad file and reran, the summary showed 1 file, and the bad file's leftovers were gone. I then deleted the test data.

**Decisions for you**
- **Run time:** you didn't give one, so I picked 23:30 UTC. That way most of the day's uploads are in, and the summary is ready before finance checks in the morning. If partners upload after that, move the cron (and mind the timezone).
- **Bad files and the summary:** if a file is still broken after its retries, that day's `summary.json` isn't written until the file is fixed and its task is cleared. I took this from "once every file is processed". If finance would rather get a partial summary, the summary task's trigger rule can be relaxed.

Not tested: a real scheduler or backfill process (I used `dags test` and a replay script against a throwaway database). I haven't committed anything.