`PartnerManifestSensor` is now deferrable (`deferrable: bool = True` by default) and keeps the same constructor arguments, so the DAGs don't change. I tested it against the stub API with mocked Variables, and ran the full DAG once on real Airflow 3.3 with `dag.test()`. In that run `wait_globex` deferred, the trigger polled until the manifest was published, the file list reached `load_globex` through XCom, and the start-time Variable was deleted at the end. Nothing is committed yet.

**Before deploying:** the triggerer needs to be able to import `partners` (specifically the new `partners.triggers`), the same way workers do. The triggerer loads triggers by class path and doesn't read DAG bundles. If it can't import it, the sensors will fail when they defer.

How each of your four points is handled:

1. **File list in XCom:** the sensor checks the API once on the worker. If the manifest is already published it returns the files straight away. Otherwise it hands off to the triggerer, and when the trigger sees the publish, the sensor returns the files as before.
2. **One time budget per DAG run:** Airflow wipes a task's XComs at the start of every try, so they can't carry the start time between retries. Instead, the time the sensor first started waiting is stored in an Airflow Variable named `partner_manifest_sensor__<dag>__<run>__<task>__<map_index>`.
   - Every try works out its deadline from that stored time, so retries don't extend it.
   - The trigger is given the deadline as a fixed point in time, so a triggerer restart doesn't extend it either.
   - When time runs out the task fails without retrying, or is skipped with `soft_fail=True`.
   - If the triggerer is down at the deadline, a backstop ends the wait about 2 minutes later.
   - If on-call clears the task, it gets a fresh budget.
   - The Variable is deleted on success or timeout. It's left behind only if a try fails on its last retry, and a later clear overwrites it.
3. **API errors fail the try, even with `soft_fail`:** errors from the trigger come back as a plain exception that the task's retries pick up. I also had to override `resume_execution`: Airflow's base sensor turns any crashed trigger into a skip when `soft_fail=True`, and now only running out of time skips.
4. **Nothing blocks the event loop:** the trigger uses `httpx` async and looks up the connection asynchronously. Creating each HTTP client was loading certificates synchronously (3–36 ms each), so it now builds one SSL context in a background thread and shares it. With 200 triggers running at once against 1-second API latency, CPU use was about 1.4 ms per poll and nothing blocked. Short lag spikes (up to ~140 ms in testing) still happen when hundreds of triggers wake at the same moment; that's ordinary scheduling, not a blocking call.

With `deferrable=False` the sensor still works the old poke/reschedule way, but in that mode `timeout` restarts with each try.

The changes are in `dags/partners/sensors.py`, a new `dags/partners/triggers.py`, an async `aget_manifest` added to `dags/partners/hooks.py`, and a short section in `README.md`. The test scripts are in `$TMPDIR/pms`, not in the repo.