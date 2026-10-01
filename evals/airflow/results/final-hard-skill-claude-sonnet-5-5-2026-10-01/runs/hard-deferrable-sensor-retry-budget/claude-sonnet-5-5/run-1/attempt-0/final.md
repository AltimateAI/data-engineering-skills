`PartnerManifestSensor` is now deferrable by default (`deferrable: bool = True`). With `deferrable=False` it falls back to the old poke path. Constructor arguments are otherwise unchanged. I ran it through `airflow dags test` against `tools/manifest_stub.py` and the four scenarios behaved as expected. I did not run a real triggerer, a triggerer restart, or the full DAG.

The sensor is in `dags/partners/sensors.py`. The new async trigger is `dags/partners/triggers.py` (`ManifestPublishedTrigger`).

1. **Manifest published.** The trigger returns the file list and `execute_complete` returns it as the task's XCom, which the load tasks read as before. The success run (`--publish-after 4 --latency 1`) ended in `success`.
2. **Timeout budget.**
   - **Start time.** The time the sensor first started waiting is saved in the task's state store, which is scoped to the DAG run and task. It survives retries and triggerer restarts. `ti.start_date` and XCom don't, because a retry resets them.
   - **Deadline.** The deadline is that start time plus `timeout`, and it is passed to the trigger as an absolute time, so a restarted trigger keeps the same deadline. Every retry checks it first and times out without deferring again.
   - **Cleanup.** The saved start time is deleted when the wait ends: on success, on timeout, and on the last try after an error.
   - **When time is up.** The sensor raises `AirflowSensorTimeout`, so it fails without retrying, or it skips when `soft_fail=True`.
   - **Tested.** With `timeout=8` and `retries=2`, the run failed about 8 seconds after it started waiting, not once per retry. The `soft_fail` run was skipped.
3. **API errors.** The trigger reports an HTTP 5xx or connection error as an event instead of raising. The sensor then raises `ManifestApiError`, which is not an `AirflowException`, so the try fails and retries take over, `soft_fail` included. In the 503 outage test with `soft_fail=1`, the task went to `up_for_retry` and then `failed`, not `skipped`.
4. **Event loop.** The trigger uses `httpx.AsyncClient`, `BaseHook.aget_connection` and `asyncio.sleep`, so nothing blocks. I didn't run the loop-stall measurement from the reference, so that point rests on the code, not a measurement.

The trigger depends on `task_state_store` in the task context, which exists on your 3.3.2 deployment. On older 3.x it would fail with a `KeyError`.

I didn't run `airflow_check.py` or `replay_runs.py`, and I haven't updated the README for the new `deferrable` argument.