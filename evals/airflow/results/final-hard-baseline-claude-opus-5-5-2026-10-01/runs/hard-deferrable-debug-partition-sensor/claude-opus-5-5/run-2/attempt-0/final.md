All seven incidents are fixed. The changes are in `dags/lake/hooks.py`, `triggers.py` and `sensors.py`. The sensor is still deferrable, its constructor and the DAGs are unchanged, and nothing is committed yet.

## Root causes and fixes

| # | Root cause | Fix |
|---|---|---|
| 1 | `aget_partition` was async in name only: it made a normal blocking `requests.get` call inside the triggerer's event loop. Every 1–2 s catalog call froze all triggers. | It now uses `httpx.AsyncClient`, which is already in `requirements.txt`. |
| 2 | The trigger computed its give-up time with `time.monotonic() + timeout` when it was created. After a triggerer restart the trigger is rebuilt, so the clock started over. | The trigger now saves an absolute clock-time `deadline`. It still accepts the old `timeout` argument, so triggers saved before the deploy load without errors. |
| 3 | A timeout raised a plain `AirflowException`, which Airflow retries. | It now raises `AirflowSensorTimeout`, which is never retried, or `AirflowSkipException` when `soft_fail=True`. |
| 4 | `execute_complete` checked only for `"timeout"`, so an `"error"` event counted as success with `files=[]`. | Error events raise `LakeApiError`, which fails the try and lets retries take over. Only an explicit `"success"` returns files. |
| 5 | The `_PUBLISHED` cache was keyed by table only, so yesterday's sensor got today's cached file list. | The key is now (connection, table, partition). |
| 6 | When the trigger finished the task itself (`TaskSuccessEvent`), Airflow 3.3 stored the XCom as a JSON *string*. `len()` of that string is 92, which is exactly the "92 files" in the logs. | The trigger now hands the files back to `execute_complete`, which returns the real list. |
| 7 | Each try started a new `timeout`. | The first try records its deadline in Airflow's `task_state_store`, which is kept per DAG run and task and survives retries. Retries wait only for whatever time is left. |

I also made the hook reject unexpected response bodies, and the sensor now gives `defer()` a timeout as a backup. That way the task still times out even if no triggerer picks it up.

## Verification
I ran the real Airflow 3.3.2 (`airflow dags test`) against `tools/catalog_stub.py`:
- **orders_diff:** "today" and "yesterday" each returned their own 2-file list, and the diff received real lists.
- **Outage with `retries=3`:** each retry waited only the remaining time (log lines like "Resuming wait; 3s of the 12.0s timeout left"). A partition that published within the total budget succeeded. One that didn't published failed by timeout at the total budget.
- **Timeouts:** a timeout gave `failed` with no further retries; with `soft_fail` it gave `skipped`.
- **Event loop and restart (5 triggers, 1.5 s API latency):** longest event-loop stall was **0.03 s**, against **4.49 s** with the old code. Rebuilding a trigger from its saved state moved its deadline by **0 s**, against **8.7 s** before.

## Trade-offs
- **Worker slot after publish:** the task now holds a worker slot for a few milliseconds to return the file list. That's what fixes #6. In 3.3.2, finishing straight from the triggerer can't return a list correctly.
- **Manual clear:** clearing the task by hand starts a new full `timeout`. Only automatic retries share the budget.
- **`deferrable=False`:** this mode still uses the standard per-try sensor timeout. The outage fix (#4) applies there too, but the shared budget across retries (#7) does not. No current DAG uses this mode.