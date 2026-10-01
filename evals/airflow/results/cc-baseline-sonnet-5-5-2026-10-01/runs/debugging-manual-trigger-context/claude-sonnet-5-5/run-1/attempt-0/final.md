I fixed `partner_feed` in `dags/partner_feed.py`. A scheduled run and a run triggered with a logical date produce the same feed as before. A manual trigger with no date now produces the feed for its UTC trigger day.

**Causes**
- **Scheduled run:** `write_manifest` read `context["execution_date"]`, which Airflow 3 removed. That is the `KeyError: 'execution_date'`.
- **Manual trigger with an empty logical date:** the run's `logical_date` is `None`. Airflow 3 then leaves `logical_date`, `ds`, `ds_nodash` and the other date keys out of the task context. That is the `KeyError: 'logical_date'` in `extract_orders`.
- **Third bug, not in your report:** `deliver` uses `{{ ds_nodash }}`. Once the first two were fixed, a no-date run would have copied files named `acme_orders_.csv`.

**Fix**
- A small `feed_day(dag_run)` helper returns the logical date if there is one, otherwise `run_after` (when the run was triggered), converted to UTC.
- `extract_orders`, `write_manifest` and the `deliver` template now all use `feed_day`. The template reaches it through `user_defined_macros`.
- Clear and re-run gives the same day, because `run_after` is stored on the run and doesn't change when you clear it.
- Output and outbox file names are unchanged, and so are the extract → manifest → deliver steps.

**Testing**
- I ran `airflow dags test` against a throwaway Airflow home, which I deleted afterwards. A run with a date (2026-03-01) produced `acme_orders_20260301.csv` and `.manifest.json` in the outbox, with the same date in the manifest.
- `dags test` without a date fills in a logical date, so it never hit the `None` case. I checked that case on `feed_day` directly with a fake run:
  - A run with no logical date and a trigger time of 23:30 at UTC-5 gives the next UTC day, 2026-10-01.
  - A run with a logical date still uses the logical date.
- I haven't run a real UI trigger with an empty date or a clear-and-rerun. The clear case rests on `run_after` being stored on the run.

Your repo has no uncommitted changes other than the edit to `dags/partner_feed.py`, and I haven't committed anything.