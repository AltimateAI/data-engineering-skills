I fixed all seven incidents in `dags/lake/hooks.py`, `triggers.py` and `sensors.py`. The sensor is still deferrable and its constructor arguments are unchanged. I didn't touch the DAGs in `dags/`.

I ran `orders_diff` end to end with `airflow dags test` against the local stub with 1 s latency. Both sensors returned their own 2-file lists, and `diff` reported 2 new files. I also ran the trigger by itself against the stub for the other outcomes:

- **Published partition:** it returned the file list.
- **Never-published partition:** it timed out at its deadline.
- **`--down` stub:** it returned an error event with `HTTP 503`.

I did not run the retry path, the soft_fail path, the triggerer-restart case or the event-loop stall measurement. The timeout-and-retry logic in `sensors.py` is untested here, including the stored start time. I also didn't run `airflow_check.py`.

| # | Root cause | Fix |
|---|---|---|
| 1 | The trigger's async call went through the blocking `requests` library, so a 1–2 s catalog call froze the triggerer loop. | `aget_partition` now uses `httpx.AsyncClient`. The sync `get_partition` and the poke path are unchanged. |
| 2 | The trigger set its stop time to now plus `timeout` when it was built. A triggerer restart rebuilt it and restarted the clock. | The trigger now takes an absolute `deadline` (epoch seconds), and `serialize()` keeps it. |
| 3 | A timeout raised a plain `AirflowException`, which the task treated as retryable. | It now raises `AirflowSensorTimeout`, which fails with no retries, or `AirflowSkipException` when `soft_fail=True`. |
| 4 | The sensor ignored `status == "error"` events and returned an empty file list as success. | It now raises `LakeApiError`, which is not an `AirflowException`. The current try fails and retries take over, even with `soft_fail`. |
| 5 | The published-partition cache was keyed by table only, so "today" got "yesterday"'s files. | The cache is keyed by `(table, partition)`. This also explains the wrong file counts in #6. |
| 6 | `TaskSuccessEvent` pushed the list as an XCom from the triggerer, and the consumers didn't get a clean list. | The trigger now sends a plain event and `execute_complete` returns the list as the task's return value. |
| 7 | Each retry deferred again with a fresh full `timeout`. | The first-wait time is stored per DAG run in `context["task_state_store"]`, so the deadline is that time plus `timeout` across retries. A retry past the deadline times out without deferring. |

- **#6 root cause:** I did not reproduce the "92 files" figure. I'm confident about the stale cache, which hands a consumer another partition's list. I didn't confirm why the XCom pushed from the triggerer came back wrong, and I replaced that path rather than debug it.
- **#6 trade-off:** the sensor now resumes on a worker for a moment to return the list, so it no longer finishes entirely inside the triggerer. The long wait still holds no worker slot.
- **Trigger signature:** `PartitionPublishedTrigger` now takes `deadline` instead of `timeout`. A trigger already deferred under the old signature will fail to rebuild after deploy, so redeploy while no sensors are deferred, or clear those tasks.
- **Test leftovers:** the 18765 stub I tried first didn't start (port in use). The other `catalog_stub.py` processes on this machine belong to other sessions and I left them alone. I removed my temporary `.af` directory, and the working tree only has the three modified files.