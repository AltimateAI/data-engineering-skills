I found and fixed the root causes of all seven incidents in `dags/lake/` (hook, trigger, sensor). The sensor is still deferrable, its constructor arguments are unchanged, and the DAGs need no edits. Nothing is committed yet.

| # | Root cause | Fix |
|---|---|---|
| 1 | `aget_partition` was `async`, but it made a blocking `requests.get` call. Every 1–2 s catalog call froze the triggerer's event loop, which delayed every other trigger. | The trigger now uses a real async request (`httpx.AsyncClient`, already in `requirements.txt`). The sync `requests` path stays for worker-side checks. |
| 2 | The trigger's deadline was computed when the trigger object was created and never saved. Each triggerer restart rebuilt it and started a fresh 2-hour timeout. | The trigger receives a fixed clock-time `deadline` and saves it, so a restart keeps it. Triggers already saved in the old format still load. |
| 3 | A timeout raised a plain `AirflowException`, which Airflow retries. | It now raises `AirflowSensorTimeout`, which fails with no retry, or `AirflowSkipException` when `soft_fail=True`. |
| 4 | `execute_complete` treated any event other than "timeout", including `"error"`, as success with `files=[]`. | API errors raise `LakeApiError`, which fails the current try and lets retries take over. With `soft_fail` it is still a retryable failure, not a skip. Non-JSON or unexpected responses also count as errors. |
| 5 | The module-level `_PUBLISHED` cache was keyed by `table` only, so `orders/today` got `orders/yesterday`'s files, or the reverse. | Removed the cache. |
| 6 | `TaskSuccessEvent(xcoms=...)` stores the list in a JSON column after already encoding it as JSON, so consumers receive a string. 92 is exactly `len('["s3://lake/orders/…/part-0.parquet", "s3://…/part-1.parquet"]')`. | The trigger now hands the file list back to the task, and `execute_complete` returns it. |
| 7 | Each retry started a new full timeout. | The sensor saves when it first started waiting in Airflow 3.3's `task_state_store`, which all retries of a task share. The deadline is that start time plus `timeout`. |

**Trade-off on #6:** the task now resumes on a worker for a moment to return the list, instead of finishing in the triggerer. The bug is inside Airflow, so finishing in the triggerer can't return a correct list until it's fixed there. The waiting itself still happens in the triggerer, so worker slots are only used briefly.

Two smaller additions:
- The sensor checks the partition once before deferring, so a partition that's already published needs no trigger.
- The deferral also has a scheduler-side timeout of the remaining time plus 60 s, as a safety net if the triggerer is down.

**Verified against `tools/catalog_stub.py` with `airflow dags test` (all of these behaved as listed):**
- **#1:** with 1.5 s API latency, the event loop never stalled for more than 36 ms.
- **#2:** a trigger rebuilt from its saved arguments after its deadline timed out immediately.
- **#3:** a timeout went straight to `failed` with retries=3; with `soft_fail` it went to `skipped`.
- **#4 and #7:** a 503 mid-wait put the task into retry. The retry deferred again and failed for good 12.0 s after the first request, which matches `timeout=12`, instead of waiting another full timeout.
- **#5:** `orders_diff` sensors each got their own partition's files, and `diff` found 2 new files.
- **#6:** after deferring, the downstream task received a `list` of 2 files.

**One behaviour to know:** the saved start time lasts for the whole DAG run. If you manually clear a sensor that has already timed out, it will time out again straight away. For a fresh window, delete the task's `wait_started_at` key through the task state store API first.