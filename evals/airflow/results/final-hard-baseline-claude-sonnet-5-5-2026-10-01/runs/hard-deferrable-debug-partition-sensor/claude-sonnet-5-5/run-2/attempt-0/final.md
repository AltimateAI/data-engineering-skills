I fixed all seven incidents in `dags/lake/`. The sensor is still deferrable and its constructor arguments are unchanged. I only ran the trigger against `tools/catalog_stub.py`, not the full sensor under Airflow.

In that run, two published partitions returned their own file lists and an unpublished one timed out. I didn't test the retry/first-start tracking, the error path or the 503 case, so those are unverified.

| # | Root cause | Fix |
|---|---|---|
| 1 | The trigger's async method called the blocking `requests`, which stalled the triggerer's event loop for the 1–2 s of each catalog call. | `aget_partition` in `hooks.py` now uses `httpx.AsyncClient`. The sync `get_partition` is unchanged. |
| 2 | The trigger set its deadline from `time.monotonic()` when it was constructed. A triggerer restart rebuilt it and restarted the clock. | The deadline is now an absolute wall-clock time that is serialized with the trigger. The new `deadline` argument is optional. |
| 3 | The sensor raised a plain `AirflowException` on timeout, which Airflow retries. | It now raises `AirflowSensorTimeout`, which isn't retried, or `AirflowSkipException` when `soft_fail` is set. |
| 4 | `execute_complete` ignored the trigger's `error` event and returned an empty file list. | It now raises `LakeApiError`, so the retries take over. It deliberately isn't an `AirflowException`, because with `soft_fail=True` Airflow would turn that into a skip and hide an outage. |
| 5 | The published-partition cache was keyed by table only, so "yesterday" got "today"'s file list. | It's now keyed by connection, table and partition. |
| 6 | `TaskSuccessEvent(xcoms=...)` stored the file list as a JSON string, so the consumer counted characters (hence 92). | The trigger now yields a normal event and `execute_complete` returns the real list. Finishing straight from the triggerer to free worker slots is gone, because I found no safe way to keep it. |
| 7 | The timeout restarted on every try. | The first try's start time is saved in an Airflow Variable keyed by dag, run, task and map index, because XComs are cleared on each try. Later tries use the time left, and if none is left the sensor fails immediately. |

For #7, the sensor now writes one Variable per task per run. If the Variable can't be read or written, the sensor logs a warning and starts the clock fresh.

I didn't change the non-deferrable path (`deferrable=False`). It still uses the base sensor's per-try timeout.