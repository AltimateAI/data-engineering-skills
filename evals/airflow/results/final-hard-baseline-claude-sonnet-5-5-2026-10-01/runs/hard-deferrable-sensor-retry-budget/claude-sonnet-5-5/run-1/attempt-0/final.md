`PartnerManifestSensor` is now deferrable by default. I checked the trigger against the local stub, but I haven't run the sensor itself in a real Airflow run.

- **What I tested:** the trigger polled the stub until the manifest was published and returned the file list. I did not exercise the timeout path, the API-error path, or the sensor's `execute`/`execute_complete`.
- **Changes:** the sensor change is in `dags/partners/sensors.py`. The new trigger is in `dags/partners/triggers.py`. The constructor arguments are unchanged, and `deferrable=False` still runs the old poke behaviour.
- **Run it for real:** one `partner_ingest` run with a short timeout, including a retry, would check the timeout and retry behaviour for real.

How it meets each point:

1. **File list:** when the manifest is published, `execute_complete` returns the files, so the load tasks still read them from XCom. `execute` also polls once before deferring and skips deferral if the manifest is already there.
2. **Timeout:** the first time the sensor starts waiting, it records the start time in an Airflow Variable keyed by dag, run, task and map index. I used a Variable because Airflow wipes the task's XComs at the start of each retry, so an XCom would have reset the clock.
   - **Deadline:** the trigger gets an absolute deadline (start plus `timeout`). A retry or a triggerer restart therefore can't extend it.
   - **Expiry:** when time is up it raises `AirflowSensorTimeout`, which Airflow doesn't retry. With `soft_fail=True` the sensor is skipped.
   - **Cleanup:** the Variable is deleted on success, on timeout, and after the last failed try. Clearing the task afterwards starts a fresh wait.
3. **API errors:** HTTP errors (any non-200, so 4xx as well as 5xx) and connection errors make the trigger report an error. The sensor then raises `ManifestApiError`, a plain exception that `soft_fail` doesn't turn into a skip, so retries take over. The wait-start Variable is kept between retries so they share one budget.
4. **No blocking:** the trigger uses `httpx.AsyncClient`, `Connection.async_get` and `asyncio.sleep`. It builds the URL with `ManifestHook.url_and_headers`, so the sync hook never runs in the triggerer. The one sync call is the first poke in `execute`, which runs on the worker.

- **Lingering Variables:** the Variable is only deleted at a final outcome. If a run is deleted or abandoned mid-wait, its Variable stays behind. They are small, but you may want an occasional cleanup of `partner_manifest_wait_start:*`.
- **Clock skew:** the deadline is a wall-clock time shared between the worker and the triggerer, so a large clock skew between those hosts would shift it.