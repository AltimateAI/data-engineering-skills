`PartnerManifestSensor` is now deferrable (`deferrable: bool = True`) and keeps the constructor arguments the DAGs use. I tested it with `airflow dags test` against `tools/manifest_stub.py` and small timeouts. I did not run it on a real triggerer, so a triggerer restart in a deploy is untested. I also did not run `airflow_check.py` or the `partner_ingest` DAG itself. I used a one-sensor test DAG instead.

**What changed**
- `dags/partners/sensors.py`: with `deferrable=False` it behaves as before (poke). Otherwise it defers to a new trigger and returns the file list from `execute_complete`, so the load tasks still read it from XCom.
- `dags/partners/triggers.py` (new): `PartnerManifestTrigger` polls the API until the manifest is published or the deadline passes. API errors come back as an error event, not a raised exception.
- `dags/partners/hooks.py`: added `ManifestHook.aget_manifest`, an `httpx` async version of `get_manifest`. The existing sync method is unchanged.

**How each on-call point is handled**
1. **File list:** the sensor returns it when the manifest is published.
2. **Total timeout:** the sensor stores when it first started waiting in the 3.3 `task_state_store`. That store survives retries and triggerer restarts, unlike XCom. Every try computes `deadline = first start + timeout` and passes that fixed deadline to the trigger, so a restarted trigger still ends at the same time. When time is up it fails for good with `AirflowSensorTimeout`, or is skipped with `soft_fail=True`. The stored start time is deleted when the wait ends, or on the last failed try. If it weren't, clearing the task later would time out immediately.
3. **API errors:** a 5xx or connection error fails the try with `ManifestApiError`, which deliberately is not an `AirflowException`. Retries take over, and `soft_fail` does not turn it into a skip.
4. **Event loop:** the trigger only uses async calls (`httpx.AsyncClient`, `aget_connection`, `asyncio.sleep`).

**Checks I ran**
- **Publish after 5s:** the sensor succeeded.
- **Timeout 6s, never published, retries=2:** it failed in about 6s with `AirflowSensorTimeout` and no retries. With `soft_fail` it was skipped.
- **Permanent 503 outage:** the task retried twice and then failed. With `soft_fail` it behaved the same way (retried, then failed, no skip).
- **Outage for the first 2s, timeout 9s:** two error retries, then a timeout at about 9s after the first start. Retries did not reset the clock.
- **Event loop and serialization:** a trigger polling a stub that takes 1s per call stalled the event loop for at most 0.04s and stopped at its deadline. It also rebuilt correctly from its `serialize()` output, which is how a restarted triggerer recreates it.

`airflow dags test` doesn't enforce the deferral timeout or restart the trigger mid-wait. So the restart behavior is covered only by the serialize round-trip above.