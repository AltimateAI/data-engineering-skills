`PartnerManifestSensor` is now deferrable by default. The trigger works against `tools/manifest_stub.py`, but I haven't run the sensor inside a real scheduler, triggerer and worker. Nothing is committed.

**What I ran against the stub**
- **Publish:** it returned the file list when the manifest was published.
- **Timeout:** it timed out on schedule when nothing was published.
- **Outage:** it reported an error right away during a 503 outage.
- **Event loop:** with the stub at 0.5s latency, a heartbeat task on the same loop kept ticking through every API call, so nothing blocked it.

I didn't exercise the sensor's `execute`/`execute_complete` paths, retries, or a triggerer restart. Those rely on my reading of Airflow's source.

**How each requirement is met**
1. **File list:** `execute_complete` returns the files, and the task returns them as its XCom value.
2. **Timeout:** the first run stores its start time in `context["task_state_store"]`, which is scoped to the DAG run and task. I read the Airflow 3.3 source and it survives retries and is cleared only on success. The deadline (start time plus `timeout`) is passed to the trigger as an absolute time, so a triggerer restart doesn't extend it. On timeout the sensor raises `AirflowFailException`, which isn't retried, or `AirflowSkipException` when `soft_fail=True` (or `never_fail`). I avoided `AirflowSensorTimeout` on purpose, because Airflow retries it.
3. **API errors:** the trigger catches any error from the hook and sends it back as an event, and the sensor raises a plain `ManifestApiError`. That fails the current try and lets retries run. Letting the trigger raise instead would have made Airflow skip `soft_fail` sensors.
4. **No blocking:** the trigger calls the hook through `asyncio.to_thread`, which also keeps the connection lookup off the loop. Each request timeout is capped to the time left before the deadline.

The new trigger is in `dags/partners/triggers.py`, and the sensor change is in `dags/partners/sensors.py`. The constructor arguments the DAGs use are unchanged.

**Things to know**
- **Clearing a task:** the start time stays in the state store until the task succeeds. If someone manually clears a task that already failed on timeout, it will time out again immediately. Deleting the `manifest_wait_started_at` key resets it.
- **Last check after the deadline:** if a retry starts after the deadline, the trigger still makes one API call before reporting the timeout. If the manifest was published in the gap, it is picked up. If that call errors, the try fails with the API error and doesn't skip.
- **Poke interval:** `exponential_backoff` and `max_wait` are ignored when deferrable. The trigger uses a fixed `poke_interval`.
- **`deferrable=False`:** this keeps the old poke behaviour, including `timeout` counted per try.
- **Triggerer import path:** the triggerer must be able to import `partners.triggers`, so the dags folder needs to be on its `PYTHONPATH`. It normally is.