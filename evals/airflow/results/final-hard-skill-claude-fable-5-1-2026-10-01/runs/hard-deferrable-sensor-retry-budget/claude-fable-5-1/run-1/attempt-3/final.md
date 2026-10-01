Done. `PartnerManifestSensor` is now deferrable by default, and every on-call requirement was exercised against the local API stub with real retries.

**Changed files**

- `dags/partners/sensors.py`: the sensor keeps its constructor arguments and gains `deferrable: bool = True`. In deferrable mode it records the first wait time in the Airflow 3.3 task state store, derives an absolute deadline from it, and defers to the trigger. It times out without deferring if a retry starts after the deadline, and drops the anchor whenever the task ends for good. With `deferrable=False` it still uses the original poke path.
- `dags/partners/triggers.py` (new): the trigger polls with `httpx.AsyncClient`, fetches the connection with the async hook API, and carries the absolute deadline in its serialized state, so a triggerer restart resumes against the original deadline. It never raises. It yields a `published`, `timeout` or `error` event and lets the sensor decide the outcome.
- `dags/partners/hooks.py`: added an async `aget_manifest` next to the sync one. `ManifestApiError` stays a plain `Exception` on purpose, so `soft_fail` cannot turn an outage into a skip.
- `README.md`: one bullet now mentions the trigger.

**How the requirements map to the code**

1. Published manifest: the trigger's event carries the file list, and the resume method returns it as the task's return value, so `acme.output` keeps working.
2. Total budget: the anchor lives in the task state store, which survives retries. The deadline rides inside the trigger, which survives triggerer restarts. `defer(timeout=)` is only a 90 s backstop in case the triggerer never delivers an event. Expiry raises `AirflowSensorTimeout` (no retries) or skips under `soft_fail`.
3. API errors: HTTP non-200 and connection errors become an `error` event, raised as `ManifestApiError`, which goes to `up_for_retry` even under `soft_fail`.
4. Event loop: no `requests`, `time.sleep` or sync connection lookup on the trigger path.

**Verified in this session** (Airflow 3.3.2, from `requirements.txt` and the installed env)

- `airflow_check.py`: exit 0, no import errors. Two pre-existing warnings about `{{ ds }}` on manual runs, unrelated to this change.
- Serialize round trip and Airflow serde round trip of the trigger kwargs pass. A trigger rebuilt from `serialize()` mid-wait stopped 0.3 s after the original deadline.
- Event-loop stall harness with a 0.6 s API latency: worst stall 43 ms.
- `airflow dags test` scenarios with retries and a 1 s retry delay:

| Scenario | Result |
|---|---|
| Publishes after 3 s | success, load task received 3 files |
| 8 s budget, 503 outage during tries 1 and 2 | same anchor on all 3 tries, failed 8 s after first wait, no further retry |
| Same with `soft_fail` | errors retried, then skipped at the deadline |
| Sustained 503 with `soft_fail`, 2 retries | failed after 3 tries, never skipped |
| Deadline passes before a retry starts | skipped immediately without deferring |
| `deferrable=False` | success via the poke path |
| Real `partner_ingest` DAG | both sensors deferred and succeeded, both loads ran |

The state-store table was empty after every scenario, so the anchor is cleaned up on success, timeout, skip and final failure.

**Not verified**: a real triggerer process and real deploy restarts. `dags test` runs triggers inline and does not enforce `defer(timeout=)`. The triggerer must have `dags/` importable so it can load `partners.triggers.PartnerManifestTrigger`, the same requirement as for any custom trigger in the DAG bundle. One behaviour to know about: clearing a task while it is `up_for_retry` keeps the original budget for that run, which matches the "counted from the first wait in that run" rule.