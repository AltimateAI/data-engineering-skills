All seven incidents trace back to five defects in `dags/lake/`. I fixed them in the hook, trigger and sensor only. The sensor stays deferrable and its constructor is unchanged, so neither DAG needed edits.

**Root causes and fixes, by incident**

1. **Blocked triggerer event loop.** The hook's async method awaited the connection but then called the blocking `requests.get`, so every 1-2 s catalog call froze every trigger in the triggerer. The async path now uses `httpx.AsyncClient`; the blocking path is kept for the worker-side poke mode only.
2. **Waits surviving a triggerer restart.** The trigger computed its give-up time from `time.monotonic()` in its constructor and serialized only the relative `timeout`. After a restart the triggerer rebuilds triggers from `serialize()`, so each restart restarted the 2 h clock, and the monotonic clock is meaningless across processes. The trigger now carries an absolute epoch `deadline`, and the sensor also passes `defer(timeout=)` as a server-side backstop for a dead triggerer.
3. **Timed-out sensors being retried.** `execute_complete` raised a generic `AirflowException`, which is retryable. It now raises `AirflowSensorTimeout`, which ends the task for good, or `AirflowSkipException` under `soft_fail`.
4. **Green sensors during a 503 outage.** `execute_complete` only checked for the timeout status; an error event fell through to `event.get("files", [])` and returned an empty list. Error events now raise the hook's `LakeApiError`, which is deliberately a plain `Exception` so the try fails and retries take over even with `soft_fail`.
5. **Same files for today and yesterday.** The in-process cache of published partitions was keyed by table name alone, so the second sensor on `orders` got the first one's file list. It is now keyed by connection, table and partition.
6. **"loading 92 files".** The trigger ended the task with `TaskSuccessEvent`, whose XCom goes through the server-side push and lands as the JSON text of the list; the 92 is the character count of that string for two files. The trigger now yields a plain event and the sensor's resume method returns the list. This costs a brief worker slot at the end of each wait.
7. **Retries restarting the 2 h budget.** Nothing anchored the budget across tries. The sensor now records the time it first started waiting in the run in the Airflow 3.3 task state store, which survives retries, with a Variable fallback for older 3.x. Each try computes the remaining budget from that anchor, times out immediately if it is spent, and clears the anchor on any final outcome so a later manual clear starts fresh.

**Verified in this session** (Airflow 3.3.2, matching `requirements.txt`, against `tools/catalog_stub.py`):

- Static checker: exit 0, no import errors. Its two warnings concern manual runs and `{{ ds }}` in the DAGs, which are pre-existing and out of scope.
- Event-loop stall with a 1 s slow API: under 50 ms, was over 1 s.
- Trigger serialize round trip, and a simulated mid-wait triggerer restart that still stopped at the original deadline.
- `airflow dags test` with small budgets: success returns a list of 2 files; timeout ends in `failed` with no retry, or `skipped` under `soft_fail`; a 503 ends in `up_for_retry` then `failed` with or without `soft_fail`; a 3 s outage with retries still timed out at the original 6 s budget; a 2 s outage followed by publication succeeded on the retry.
- Real DAGs: `lake_ingest` logs "loading 2 files into orders", and `orders_diff` sees two distinct partitions.

**Not verified:** a real multi-process triggerer and scheduler, and the server-side deferral timeout itself, which `dags test` does not enforce. One deploy note: the trigger's serialized arguments changed, so sensors already deferred at deploy time will fail their current try when the new triggerer cannot rebuild the old trigger, then retry cleanly under the new code.