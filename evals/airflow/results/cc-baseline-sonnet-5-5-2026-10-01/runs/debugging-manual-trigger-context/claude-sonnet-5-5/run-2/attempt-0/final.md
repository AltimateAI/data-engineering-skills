I fixed both failures in `dags/partner_feed.py`, and I ran the DAG locally with `dag.test()` for both start modes. Both runs succeeded and wrote the right files.

**Cause**
- **Scheduled run:** `write_manifest` read `context["execution_date"]`, which Airflow 3 removed. That is the `KeyError: 'execution_date'`.
- **Manual trigger with no date:** Airflow 3 sets `logical_date` to `None` for these runs. `extract_orders` hit `KeyError: 'logical_date'`. `deliver` would have failed next, because its `ds_nodash` template is also unavailable when there's no logical date.

**Fix**
- **Shared helper:** a new `feed_day()` helper picks the day. It uses `dag_run.logical_date` when there is one, and otherwise `dag_run.run_after`, which is the trigger time. It converts the result to UTC.
- **All three steps use it:** `extract_orders`, `write_manifest` and the `deliver` template (which now builds its date from `dag_run` instead of `ds_nodash`) all get the same day.
- **Clear and re-run:** `run_after` is stored on the DAG run, so clearing and re-running a manual run tomorrow still produces the trigger day's feed.
- **Unchanged:** the output and outbox file names, and the extract → manifest → deliver steps.

**Test**
- **With a logical date:** `2026-03-02` produced `output/partner_feed/2026-03-02/` and `outbox/acme/acme_orders_20260302.csv` and `.manifest.json`.
- **Without one:** `logical_date=None` with `run_after` at 2026-03-03 23:59 UTC produced the 2026-03-03 feed. Its manifest had `partition: 2026-03-03` and `row_count: 6`.
- **Not tested:** the UI trigger and the clear-and-re-run case. For clear and re-run, I'm relying on `run_after` being stored per run.
- **Cleanup:** I deleted the test output and scratch files, so `git status` shows only the DAG change.