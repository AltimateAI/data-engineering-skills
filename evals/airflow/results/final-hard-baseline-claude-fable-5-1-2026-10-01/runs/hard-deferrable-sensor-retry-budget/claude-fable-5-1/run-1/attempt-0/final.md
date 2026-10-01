`PartnerManifestSensor` is now deferrable by default, verified with 31 unit tests and a live run against a real Airflow 3.3.2 scheduler and triggerer. Changes are uncommitted in the working tree.

**What changed**

- `dags/partners/triggers.py` (new): `PartnerManifestTrigger` polls the API with `httpx` and an awaited connection lookup, so nothing blocks the triggerer's loop. It never raises. Every outcome is an event with a status of `published`, `timeout`, or `error`. That matters because an exception escaping a trigger becomes `TaskDeferralError`, which the base sensor converts into a skip for soft_fail sensors.
- `dags/partners/sensors.py`: constructor keeps `partner`, `ds`, `manifest_conn_id` and adds `deferrable: bool = True`. The sensor computes an absolute deadline, defers, and `execute_complete` returns the file list, raises `AirflowSensorTimeout` or `AirflowSkipException` at the deadline, or raises `ManifestApiError` on API errors so retries apply. It overrides `resume_execution` so soft_fail applies only to timeouts, not to outages or trigger crashes. `deferrable=False` keeps the poke loop with the same budget.
- `dags/partners/hooks.py`: added `aget_manifest`, the async counterpart of `get_manifest`.
- `tests/` (new) and a README section.

**How the timeout budget survives retries and restarts**

XComs for a task are deleted at the start of every try, and Airflow 3.3 also wipes TaskReschedule rows and regenerates the TI id on retry, so neither works. The sensor stores its first start time in Airflow 3.3's task state store, which is scoped to the task instance across tries. The deadline also travels in the serialized trigger kwargs, so a restarted triggerer rebuilds the trigger with the same deadline. Clearing a task does not clear the state store, so the sensor uses Airflow's own rule to detect a fresh wait: the first try after a clear is `max_tries - retries + 1`, and only that try overwrites the stored start.

**Live verification** on standalone Airflow with the stub API:

- Published manifest: file list in XCom, downstream load ran.
- Outage (two 503s): two retries, each log line shows the same start time and a shrinking budget, then success.
- Hard timeout with an outage inside it: failed at the deadline with a retry still available but not used.
- Soft timeout: skipped at the deadline, downstream load skipped.
- Triggerer killed for 10 seconds mid-wait: polling resumed, one sensor published afterwards, another timed out 3 seconds after its original deadline.
- Clearing a timed-out sensor via the REST API: fresh 60-second budget, stored start replaced.

**Things to know**

- The triggerer imports triggers by class path and does not add the DAG bundle to `sys.path`, so `dags/` must be on the triggerer's `PYTHONPATH`. Workers get it from the bundle already.
- As a backstop for a dead triggerer, the scheduler-side trigger timeout is set to the deadline plus 60 seconds, so the trigger's final call at the deadline can be delivered first.
- The triggerer logged two "blocked for 0.20 seconds" warnings exactly at the threshold, one before any trigger had started. Importing the trigger module costs 0.06s, and the unit test with 1-second API latency shows loop gaps under 0.3s, so I attribute these to the single-laptop SQLite setup.
- A retry that begins after the deadline ends the wait immediately without a final API call.