I fixed all seven incidents in `dags/lake/`, with the sensor still deferrable and its constructor arguments unchanged. I ran the trigger against the local catalog stub and the new sensor module imports cleanly. I did not run a DAG end-to-end, so the sensor's retry and timeout behaviour is untested.

**Root causes and fixes**

1. **Blocked event loop:** `aget_partition` called blocking `requests` inside the triggerer's event loop. It now runs through `asyncio.to_thread`, so a 1–2 s catalog call no longer stalls other deferred tasks (`hooks.py`).
2. **Timeout reset on triggerer restart:** the trigger kept its deadline as `time.monotonic() + timeout`, so a restart gave it a fresh full timeout. It now takes an absolute epoch `deadline` that survives restarts and is serialized with the trigger (`triggers.py`).
3. **Timeout retried:** a timeout raised a plain `AirflowException`, which retries. It now raises `AirflowFailException`, which fails for good, or `AirflowSkipException` when `soft_fail=True`.
4. **503s went green:** the trigger sent an `error` event, but `execute_complete` ignored its status and returned an empty file list. Any status other than `success` now raises, so the try fails and the task's retries take over.
5. **Same file list for "today" and "yesterday":** the published-partition cache was keyed by table only. It is now keyed by `(conn, table, partition)`.
6. **Absurd file counts:** I believe `TaskSuccessEvent(xcoms=...)` stored the list as a JSON string, so `len()` counted characters; I did not reproduce this. The trigger now yields a normal event with the files and `execute_complete` returns the list. This costs a short worker slot at the end of each wait, which the earlier "finish from the triggerer" change was meant to avoid, but it is the only way the sensor's return value is guaranteed to be the list.
7. **Timeout restarted on retry:** the deadline now counts from the first time the sensor started waiting.
   - I store that start time in an Airflow Variable keyed by dag, run, task and map index. XComs are cleared at the start of each fresh try, so they can't carry it across retries.
   - A retry reuses the stored start, and if the deadline has already passed it fails immediately.
   - The entry also records which try-round it belongs to, so clearing the task and re-running starts a fresh clock.
   - This leaves one Variable per sensor per DAG run; you may want to clean those up.

**Other changes**
- The trigger now polls once before checking the deadline, so a timeout of 0 still checks the catalog.
- The non-deferrable path also fails without retrying on timeout.
- Triggers already serialized with the old `timeout` argument would not deserialize after deploying, so drain deferred sensors first or expect those few to fail and retry.

I didn't commit anything.