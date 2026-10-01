`PartnerManifestSensor` is now deferrable by default on Airflow 3.3.2 and all four on-call rules were exercised with real `airflow dags test` runs against the stub.

**Changed files**

- `dags/partners/sensors.py`: `deferrable: bool = True` and `request_timeout` added; the existing `partner`, `ds`, `manifest_conn_id` arguments and the `poke` path are unchanged. In deferrable mode, `execute` records the moment the task first starts waiting in the run-scoped task state store, computes an absolute deadline from it, and defers with that deadline. `execute_complete` returns the file list, times out, or re-raises the API error.
- `dags/partners/triggers.py` (new): `PartnerManifestTrigger` polls with the async hook method and carries the absolute deadline in `serialize()`, so a rebuilt trigger keeps the original clock. It yields `published`, `timeout`, or `error` events and never raises.
- `dags/partners/hooks.py`: added `aget_manifest` using `httpx.AsyncClient` and `aget_connection`. The sync method stays for poke mode. `ManifestApiError` is documented as a plain `Exception` on purpose.

**How each rule is met**

1. The resume method returns the file list, so it lands in the `return_value` XCom that the load tasks read.
2. The anchor lives in `context["task_state_store"]`, which a retry does not clear, and the trigger's deadline is absolute, so a triggerer restart does not reset it. When the deadline passes the sensor raises `AirflowSensorTimeout` (no retries) or `AirflowSkipException` under `soft_fail`, and deletes the anchor so a later manual clear starts a fresh wait.
3. The trigger reports an HTTP 5xx or connection error as an event; the sensor raises `ManifestApiError`, which is not an `AirflowException`, so the try fails and the task's retries run even with `soft_fail`.
4. The trigger uses only `await`-able calls: async connection lookup, one long-lived `httpx.AsyncClient`, and `asyncio.sleep`.

**Verified in this session**

- Static checker on `dags/`: exit 0, no errors. Two pre-existing warnings about `{{ ds }}` on manual runs are unchanged by this work.
- Serialize round trip, plain and through Airflow's serde: identical.
- Event-loop harness with a 0.7 s API stub across several polls: worst stall 69 ms.
- `dags test` success path: `wait` and `load` succeeded; XCom held the three file paths.
- `dags test` with an 8 s budget and a 503 outage mid-wait: three tries, the retries logged the same deadline, and the task failed within 0.02 s of that deadline. With `soft_fail=True` the earlier tries went to retry, not skip, and the final state was skipped at the deadline.
- `dags test` with a full outage and `soft_fail=True` and a 60 s budget: three tries, final state failed, done in 7 s. State store rows were cleaned up in every run.
- `dags test` with `deferrable=False`: poke path succeeded.
- Restart simulation: trigger cancelled after 3 s, rebuilt from its serialized form, and it timed out 6.3 s after the original start on a 6 s budget.
- Unit check: a retry starting after the deadline raises the timeout or skip immediately and deletes the anchor.

**Not verified**

- A real triggerer process and a real deploy restart. `dags test` runs triggers inline and does not enforce the `defer(timeout=)` backstop.
- The `Variable`-based fallback store, which only applies on 3.x releases without `task_state_store`.
- The task state store is not reset when a task is cleared while deferred, so a clear mid-wait continues the original budget rather than starting over.