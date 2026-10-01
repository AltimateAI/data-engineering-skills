`PartnerManifestSensor` is now deferrable by default and meets all four requirements. I tested it locally with `airflow dags test` against the stub, but not on a real triggerer. The DAGs need no changes: the constructor arguments are the same, plus `deferrable: bool = True`. Nothing is committed.

**What changed**
- **`dags/partners/triggers.py`** (new): `PartnerManifestTrigger` polls the API from the triggerer. It sends back exactly one result: published with the file list, timed out, or an API error.
- **`dags/partners/sensors.py`**:
  - **Timeout:** the first try that starts waiting stores its start time in `context["task_state_store"]`. That store is per DAG run and task, and every retry shares it. The deadline is that start time plus `timeout`, and the trigger gets it as a fixed timestamp. Retries can't reset it, and a triggerer restart rebuilds the trigger with the same deadline.
  - **Out of time:** the sensor fails without retries, or is skipped when `soft_fail=True`.
  - **API errors:** the trigger reports the error rather than crashing, and the sensor then raises `ManifestApiError`. Airflow's sensor code only turns its own exceptions into skips under soft_fail, so this one fails the try and the retries take over. A crashed trigger also fails the try instead of skipping.
  - **Clean-up:** the stored start time is deleted when the wait ends for good (success, timeout, or failure on the last try). Without that, clearing the task later would make it time out immediately.
  - **`deferrable=False`:** the old poke path still works and now uses the same run-wide deadline.
- **`dags/partners/hooks.py`**: added `aget_manifest()`, which uses httpx and the async connection lookup so nothing blocks the event loop. The existing `get_manifest()` is unchanged.

**Test results (Airflow 3.3.2, timeout 8 s, polling every 1 s)**
- **Static check:** exits 0. Its two warnings are about the existing `{{ ds }}` default (see below).

| Scenario | Result |
|---|---|
| Manifest published | Success; `load` received the 3 files from XCom |
| Outage forces a retry, manifest never published | Ended 9.5 s after the first try started (on try 2 of 3) with a timeout and no further retries. Without the fix, the retry would have started a fresh 8 s. |
| Same, with `soft_fail` | The outage went to retry rather than skip; skipped at 9.6 s, once the time was up |
| `soft_fail` with a permanent outage | Failed, not skipped |
| `deferrable=False` | Success with the file list; timed out at 10.5 s across a retry |
| Real `partner_ingest` DAG | Both sensors succeeded; `load_acme` and `load_globex` loaded 3 files each |

- **Triggerer restart:** I stopped the trigger after 2.5 s and rebuilt it from its saved state. It still stopped at the original 5 s deadline (5.5 s including the final poll).
- **Event loop:** the longest stall was 0.04 s while the API took 1 s per call.
- **Clean-up:** the stored start time was gone after every run that ended.

The run times include about 1.5 s of task startup. The poke path can overshoot by up to one `poke_interval`.

**Not verified**
- **Real triggerer:** a real restart during a deploy, and hundreds of triggers running together, were not tested; the restart was only simulated in a script.
- **Imports on the triggerer:** it must be able to import `partners.triggers` and have `httpx` installed (it's in `requirements.txt`). The DAGs already import `partners.*` from the dags folder, but I haven't confirmed that on your triggerer.
- **Anchor left behind:** if a worker is killed on its last try, the stored start time stays. Clearing that task later would then time out immediately.

**Not changed:** the `ds="{{ ds }}"` default doesn't render on Airflow 3 manual runs that have no logical date. That was already the case before this change, and I didn't touch it.

My test DAG and scratch Airflow home are in `../pms_test`, outside the repo; you can delete them.