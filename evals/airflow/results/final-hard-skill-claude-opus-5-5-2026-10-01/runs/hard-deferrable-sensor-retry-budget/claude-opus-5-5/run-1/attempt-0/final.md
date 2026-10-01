`PartnerManifestSensor` is now deferrable by default (`deferrable: bool = True`). The constructor arguments the DAGs use are unchanged, and `dags/partner_ingest.py` needed no edits. I ran it end to end on the installed Airflow 3.3.2 against the stub and it passed; it hasn't run under a real triggerer.

**What changed**
- **`dags/partners/triggers.py` (new):** a trigger that polls the API. It is given a fixed deadline, so a trigger rebuilt after a triggerer restart stops at the same time as before. It reports every outcome (published, time's up, error) back to the sensor and never raises. Under `soft_fail`, any Airflow exception coming back from the triggerer becomes a skip, so raising would turn an outage into a skip.
- **`dags/partners/hooks.py`:** a new non-blocking `aget_manifest` that uses `httpx` and looks up the connection without blocking. The existing `get_manifest` is unchanged.
- **`dags/partners/sensors.py`:**
  - On the first try in a DAG run, the sensor saves "first started waiting" in Airflow 3.3's per-task state store, which survives retries (XCom is wiped on each retry). Every try works out the deadline as that start time plus `timeout`, on both the deferrable and the poke/reschedule paths.
  - When time is up, the task fails without retries, or is skipped with `soft_fail`.
  - An API error raises `ManifestApiError`, which is not an Airflow exception, so the try fails and retries run, also with `soft_fail`.
  - If the trigger itself crashes in the triggerer, Airflow's default would also skip a `soft_fail` sensor. I changed that so it fails the try and retries instead.

**How on-call's four requirements were checked** (test DAG with `timeout=8`, `poke_interval=1`, `retries=2`, against the stub)
1. **File list:** the manifest was published and `load` received the 3 files from XCom. This passed on both paths and in the real `partner_ingest` DAG.
2. **Total timeout:** a 503 partway through caused 2 retries. Try 1 started at 12:39:07.4 and the sensor timed out at 12:39:15.5, 8.1 s after that first start, when the last try had been running only 3.9 s. The result was `failed`, or `skipped` with `soft_fail`. Same outcome on the poke path.
   - For triggerer restarts, I rebuilt the trigger from its saved state partway through the wait, and it still stopped at the original deadline.
3. **API errors:** with a constant 503, a `soft_fail` sensor went through its retries and ended `failed`, not skipped, on both paths. A refused connection also comes back as an error.
4. **Event loop:** with the stub taking 1 s per call, the longest stall on the event loop was 0.002 s. The only exception is a one-time 0.06 s the first time a triggerer process creates an `httpx` client. The trigger code makes no blocking calls (no `requests`, `time.sleep`, or sync connection lookups).

**Before you deploy**
- **The triggerer must be able to import `partners.triggers`.** Airflow 3.3's triggerer doesn't add the DAGs folder to its Python path, so put `dags/` on the triggerer's `PYTHONPATH` or install `partners` as a package. Otherwise the trigger can't load: each try fails and retries, then the task fails, and the wait never actually runs.
- **The wait can run slightly over `timeout`:** by up to one API call, plus one poll interval if the triggerer is slow to report.
- **A clear starts a fresh budget once the wait has ended:** the saved start time is deleted on success, on timeout, and when the last try fails. If someone clears the task while it is still retrying, the original budget carries on.

**Not verified:** a real triggerer process, real deploy restarts (only simulated in-process), and your deployment's Python path. There's also an old issue I didn't change: the default `ds="{{ ds }}"` doesn't render on manual runs, which have no logical date in Airflow 3.