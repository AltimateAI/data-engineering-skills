I fixed all seven incidents. The changes are only in `dags/lake/hooks.py`, `triggers.py` and `sensors.py`. The sensor is still deferrable, its constructor is unchanged, and `dags/lake_ingest.py` and `dags/orders_diff.py` are untouched. Nothing is committed yet.

## Root causes and fixes

| # | Cause | Fix |
|---|---|---|
| 1 | The trigger's async method `aget_partition` called the blocking `requests.get`, so each 1–2 s catalog call froze the shared triggerer loop for every DAG. | It now uses `httpx.AsyncClient`, which is already pinned in `requirements.txt`. Network errors and non-200 answers become `LakeApiError`. The non-deferrable path still uses `requests`. |
| 2 | The give-up time was `time.monotonic() + timeout`, worked out when the trigger was built. A triggerer restart rebuilds the trigger, which started a fresh 2 h every time. | The trigger now saves an absolute `deadline` (UTC seconds) with its state. Triggers still waiting from the old code still load and get a new 2 h, once. |
| 3 | A timeout raised a plain `AirflowException`, which Airflow retries. | A timeout now raises `AirflowSensorTimeout`, which fails with no retries, or skips under `soft_fail=True`. As a backstop, the deferral has an Airflow-side timeout set to the remaining time plus 60 s. |
| 4 | `execute_complete` ignored the trigger's `"error"` event and returned `event.get("files", [])`, so outages counted as success with no files. | API errors now raise `LakeApiError`. Airflow doesn't turn that into a skip, so the try fails and retries take over, even under `soft_fail`. |
| 5 | The module-level cache `_PUBLISHED` was keyed by table only, so "today" got "yesterday's" files (or the other way round). It was also shared by every trigger in the triggerer. | Cache removed. |
| 6 | Finishing straight from the triggerer stored the file list wrongly; 92 is probably the character count of the list stored as one string, but I didn't confirm that. `airflow dags test` doesn't support finishing from the triggerer at all. | The trigger sends a normal `{"status": "published", "files": [...]}` event, and `execute_complete` returns the list. |
| 7 | Each try started a new `timeout`. | The time the sensor first started waiting is saved in Airflow 3.3's per-task state store (`task_state_store`), which survives retries. Every try uses that start time plus `timeout`, and returns at once if that has passed. The saved time is deleted on success, on timeout and after the last failed try. The non-deferrable path follows the same rule. |

**Trade-off from #6:** finishing now takes a worker slot for a fraction of a second, to run `execute_complete`, instead of none.

## What I checked
I ran these on Airflow 3.3.2 with `airflow dags test` against `tools/catalog_stub.py`. The test DAGs used `timeout=8`, `retries=2`, and a retry delay of 1–3 s.
- **Static check:** clean, with no import errors. Two warnings remain, about the existing `{{ ds }}` default not working on manual runs in Airflow 3. I left that as is.
- **Success:** the sensor checked the catalog several times, then returned 2 files. `lake_ingest` logs "loading 2 files into orders/customers". `orders_diff` gets two different file lists and reports "2 new files".
- **Never published:** the task failed once after 8 s with no retries. With `soft_fail` it was skipped.
- **Every call returns 503, and connection refused:** 3 tries, then failed. With `soft_fail` it still fails rather than skipping. Both modes behave the same.
- **5-minute-outage case:** with a 503 outage, the sensor first waited at 12:39:26.8, was retried twice, and timed out at 12:39:34.8. That is 8.0 s in total, so retries don't restart the clock.
- **Triggerer restart:** I rebuilt a trigger from its saved state partway through a 4 s wait, and it still stopped 4.0 s after the original start.
- **Event loop:** with the stub answering in 1 s, the worst stall was 0.03 s. There are no blocking calls left in `triggers.py`.

## Not checked, and caveats
- I didn't run a real triggerer or scheduler; `dags test` runs triggers in the same process.
- If the 60 s backstop deferral timeout fires, for example because the triggerer was down, or if a worker crashes, the saved start time isn't deleted. Clearing that task later in the same DAG run would then time out immediately.
- The saved start time expires after the state store's default retention period.