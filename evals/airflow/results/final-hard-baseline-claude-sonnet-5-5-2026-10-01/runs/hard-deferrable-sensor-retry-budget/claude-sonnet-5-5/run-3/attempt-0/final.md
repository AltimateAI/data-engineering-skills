`PartnerManifestSensor` is now deferrable by default (`deferrable=True`) and keeps its existing constructor arguments. Pass `deferrable=False` to get the old poke behaviour. I tested the trigger against the stub: it returned the file list after about 3s of waiting, and a refused connection produced an error event. I did not run the sensor inside a real scheduler and triggerer, so deferral, retries and triggerer restarts are untested. The timeout path, the 503 path and a check that nothing blocks the event loop were not run either.

- **File list:** when the manifest is published, `execute_complete` returns the files, so the load tasks still read them from XCom.
- **Timeout:** the first time the sensor waits in a run, it saves its start time in Airflow 3.3's task state store (`context["task_state_store"]`). That store is keyed by run and task, not by try, so retries don't reset it.
    - The sensor computes an absolute deadline from that start time and passes it to the trigger, so a triggerer restart resumes against the same deadline.
    - A retry that starts after the deadline has passed fails immediately.
    - On timeout the sensor raises `AirflowSensorTimeout`: no retry, and it becomes a skip with `soft_fail=True`.
    - The deferral also carries a timeout of the deadline plus 2 minutes. It's a backstop in case the trigger is lost; the trigger enforces the real deadline.
- **API errors:** the trigger turns any exception, including a 5xx, a connection error or bad JSON, into an error event. The sensor raises `ManifestApiError`, which is not an `AirflowException`. Airflow's `soft_fail` handling only converts `AirflowException` into a skip, so an outage fails the try and retries apply, even for globex.
- **Event loop:** there is a new `ManifestPublishedTrigger` in `dags/partners/triggers.py`. It uses a new `ManifestHook.aget_manifest`, which fetches the connection with `Connection.async_get` and calls the API with `httpx.AsyncClient`. Requests are cut off at the deadline.

`dags/partners/hooks.py` and `dags/partners/sensors.py` are modified, and `dags/partners/triggers.py` is new.

- **Stored start time:** the saved start time is deleted when the sensor succeeds or times out, so clearing the task by hand starts a fresh wait. If the retries run out on API errors and someone then clears the task, the old start time is still there, so the timeout counts from the original start.
- **Triggerer path:** the triggerer needs `dags/` on its Python path to import `partners.triggers`. It already needs this for `partners.hooks`.