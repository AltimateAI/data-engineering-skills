`PartnerManifestSensor` is now deferrable by default (`deferrable=True`). The DAG-facing constructor arguments are unchanged, so `partner_ingest.py` needed no edits. I ran it against the local stub and the four on-call requirements held. I did not test a real triggerer restart.

**What changed**
- `dags/partners/hooks.py`: added `ManifestHook.aget_manifest`, an async version of `get_manifest` that uses `httpx` and `aget_connection`. The sync `get_manifest` is unchanged.
- `dags/partners/triggers.py` (new): `ManifestPublishedTrigger` polls with `await asyncio.sleep` and takes an absolute `deadline`. It ends with a published, timeout or error event.
- `dags/partners/sensors.py`: the sensor stores when it first started waiting in the task state store (`task_state_store`, new in Airflow 3.3) and sets `deadline = first_start + timeout`. That store survives retries and triggerer restarts. `deferrable=False` keeps the old poke path.

**On-call requirements**
1. **File list:** the published event's file list is returned from `execute_complete`, so it lands in XCom as before.
2. **Timeout:** retries and restarts don't reset the clock, because the deadline is absolute and the stored start time is reused. At or past the deadline the sensor fails with `AirflowSensorTimeout`, or skips if `soft_fail=True`.
3. **API errors:** an HTTP error or connection error makes the trigger send an error event. The sensor then raises `ManifestApiError`, which isn't an `AirflowException`, so the task's retries take over, including under `soft_fail`.
4. **Event loop:** the trigger makes no blocking calls.

The stored start time is cleared on success, on timeout, and on the final try, so a later clear-and-rerun starts a fresh budget. It is kept between retries so they share one budget.

**Checked** (`airflow dags test`, local stub, `retries=2`):
- **Success:** a published manifest returns the file list.
- **Timeout:** with `timeout=6` and 2 retries the task failed about 6 seconds after it started waiting, not after 3 × 6.
- **Timeout with `soft_fail`:** skipped on the same budget.
- **Outage with `soft_fail`:** a 503 gave `up_for_retry`, not a skip. The outage outlasted all 3 tries, so the task ended failed. I did not get a retry that recovers into success.
- **Trigger:** it rebuilds identically from `serialize()`. With 1 second API latency the worst event-loop stall was about 0.03 seconds.

**Not tested**
- A real triggerer, including a restart mid-wait.
- `defer(timeout=)` enforcement, which `dags test` doesn't do.

**Deploy note:** the triggerer must be able to import `partners.triggers`, so the dags folder has to be on its Python path, as it is for the workers.

I didn't run `airflow_check.py` or commit anything. The scratch test files were deleted.