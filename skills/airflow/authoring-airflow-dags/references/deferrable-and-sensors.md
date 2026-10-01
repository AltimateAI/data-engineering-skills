# Sensors, deferrable operators and triggers

Read this when you add or change a sensor, make an operator or sensor deferrable, write a trigger,
or when a sensor's `timeout`, retries or `soft_fail` behaviour matters. Every 3.x statement below was
checked on Airflow 3.3.2 by running it, or by reading the 3.3.2 source where a run can't show it.
On another 3.x minor, re-check the APIs marked *3.3* in the project env before relying on them.

## 1. Choosing a mode

| mode | holds a worker slot while waiting | needs | use when |
|---|---|---|---|
| `poke` (default) | yes, for the whole wait | nothing | waits of seconds |
| `reschedule` | no; the task re-runs every `poke_interval` | nothing | default for long waits, works everywhere |
| `deferrable=True` | no; a trigger waits in the triggerer | a running triggerer and a trigger class | many long waits, or the user asks for it |

Always set `timeout` in seconds to match the requirement. The default is 7 days. Also set a sensible
`poke_interval`. Point a file sensor at the exact file for the run's day, templated from the date
helper, not at the directory. `FileSensor` needs an `fs` connection (`fs_conn_id`, default `fs_default`).

## 2. Anatomy of a deferrable operator (3.x)

```python
class JobDoneSensor(BaseSensorOperator):              # from airflow.sdk import BaseSensorOperator
    def __init__(self, *, job_id: str, deferrable: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.job_id, self.deferrable = job_id, deferrable

    def execute(self, context):
        if not self.deferrable:
            return super().execute(context)           # the classic poke/reschedule path
        deadline = ...                                 # absolute, see section 4
        self.defer(trigger=JobDoneTrigger(job_id=self.job_id, deadline=deadline,
                                          poll_s=self.poke_interval),
                   method_name="execute_complete",
                   timeout=max(deadline - utcnow(), timedelta(seconds=1)))

    def execute_complete(self, context, event, **_):  # event = the TriggerEvent payload
        if event["status"] == "done":
            return event["files"]                      # becomes the task's return_value XCom
        if event["status"] == "timeout":
            raise AirflowSensorTimeout(...)           # see section 5 for errors
        raise UpstreamApiError(event["message"])
```

```python
class JobDoneTrigger(BaseTrigger):                     # from airflow.triggers.base import BaseTrigger, TriggerEvent
    def __init__(self, job_id: str, deadline: datetime, poll_s: float):
        super().__init__()
        self.job_id, self.deadline, self.poll_s = job_id, deadline, poll_s

    def serialize(self):
        return (f"{type(self).__module__}.{type(self).__qualname__}",
                {"job_id": self.job_id, "deadline": self.deadline, "poll_s": self.poll_s})

    async def run(self):
        while True:
            ...                                        # one async API call, section 3
            if datetime.now(timezone.utc) >= self.deadline:
                yield TriggerEvent({"status": "timeout"}); return
            await asyncio.sleep(self.poll_s)
```

Contract details that bite:

- **`serialize()` is the trigger's only state.** The triggerer rebuilds the trigger from
  `classpath(**kwargs)` after every triggerer restart or deploy, and anything set during `run()` is
  lost. So pass an **absolute** deadline (a tz-aware `datetime` or an epoch float), never "now +
  timeout" computed in `__init__` or `run()`, which restarts the clock on every restart. Every
  constructor argument must appear in the kwargs, and the classpath must be importable in the
  triggerer's environment.
- Kwargs round-trip through Airflow's serde. A `datetime` comes back as a `datetime` and a `tuple`
  as a `tuple`, but the event payload reaches `execute_complete` as JSON-like data (a tuple becomes
  a list). Keep both to primitives and datetimes.
- **Check the round trip without a triggerer:**
  `path, kw = trig.serialize(); mod, _, name = path.rpartition("."); clone = getattr(importlib.import_module(mod), name)(**kw); assert clone.serialize() == (path, kw)`.
- **`method_name` must be a string on 3.3**, even when the trigger ends the task itself.
  `method_name=None` fails with `ValidationError ... DeferTask next_method`.
- **`defer(kwargs=...)`**: a real triggerer passes them to the method together with `event`. But
  `airflow dags test` passes only `event`, so give such parameters defaults, or carry the data in
  the event instead.
- Return value of the resume method = the task's `return_value` XCom, as for `execute`.

## 3. Nothing in `run()` may block the event loop

One triggerer runs hundreds of triggers on one asyncio loop. A blocking call stalls all of them. In
production the triggerer then logs `Triggerer's async thread was blocked for N seconds`.

- HTTP: `httpx.AsyncClient` (`async with httpx.AsyncClient(timeout=...) as c: r = await c.get(...)`).
  Check that the client library is installed in the env; don't assume `aiohttp` is.
- Connections: `conn = await BaseHook.aget_connection(conn_id)` (or `await Connection.async_get(conn_id)`).
  Not the sync `get_connection`, `Variable.get`, or a sync hook method.
- Waiting: `await asyncio.sleep(...)`, never `time.sleep`.
- A sync library you cannot replace: `await asgiref.sync.sync_to_async(fn)(*args)` runs it in a
  thread. Add an async method to the hook (`async def aget_status(...)`) and keep the sync one for
  the poke path.
- Make the per-request timeout shorter than the poll interval.

**Measure it.** Run the trigger once with a heartbeat coroutine beside it. A stall of more than
about 0.1 s means something blocks. Measured on 3.3.2: a `time.sleep(0.5)` call stalled the loop
0.51 s, and the same call wrapped in `sync_to_async` stalled it 0.002 s. With `debug=True`, asyncio
also logs `Executing <Task ...> took 0.510 seconds`.

```python
async def heartbeat(stop):
    worst = 0.0
    while not stop.is_set():
        t = time.monotonic(); await asyncio.sleep(0.01)
        worst = max(worst, time.monotonic() - t - 0.01)
    return worst

async def measure(trigger):
    stop = asyncio.Event(); hb = asyncio.create_task(heartbeat(stop))
    await asyncio.sleep(0)          # start the heartbeat first, or a blocking first call goes unseen
    try:
        event = await anext(trigger.run())
    finally:
        stop.set()
    return event, await hb          # point the trigger at a stub or slow test endpoint

print(asyncio.run(measure(JobDoneTrigger(...)), debug=True))
```

## 4. Timeouts, retries and a budget that survives both

- **`defer(timeout=X)` counts from the moment of that deferral**: the API server stores `now + X`.
  Every retry and every re-deferral gets a fresh X. When it expires, the task resumes with
  `TaskDeferralTimeout`. A sensor turns that into `AirflowSensorTimeout`, which fails the task
  **without retries**, or skips it under `soft_fail`.
- A sensor's `timeout` in deferrable mode is only what you implement. Nothing built in keeps one
  clock across retries.
- **"Timeout is the total wait in this DAG run, retries included"** needs an anchor: the first time
  this task started waiting in this run. Store it where a retry can read it, then compute
  `deadline = anchor + timeout`. On every try: if the deadline has passed, time out without
  deferring. Otherwise defer with the absolute deadline in the trigger and
  `timeout=deadline - now` (plus a little slack).

Where an anchor survives a retry (measured on 3.3.2 with `airflow dags test` and real retries):

| store | survives a retry? | notes |
|---|---|---|
| XCom (`ti.xcom_push`) | **no** | a retry clears the task's XComs before it runs |
| `ti.start_date` | no | new for every try |
| `dag_run.start_date` | no | the run's start, not this task's first wait; `dags test` sets it to the logical date |
| `context["task_state_store"]` (*3.3*) | **yes** | scoped to (DAG run, task, map index); `.get(key)`, `.set(key, json_value)`, `.delete(key)`; check `"task_state_store" in context` on older 3.x |
| `Variable` | **yes** | key it by `dag_id`/`run_id`/`task_id`/`map_index`; see below |

- **`Variable.set` only accepts `str` on the 3.x Task SDK.** `Variable.set(k, time.time())`, an
  int or a dict raises `ValidationError ... PutVariable value Input should be a valid string`
  on every try. Store `str(value)` or use `Variable.set(k, obj, serialize_json=True)`, and parse the
  value back when you read it.
- Delete the anchor when the wait ends: on success, on timeout, and on the last try. Neither store
  resets when someone clears the task later, so a stale anchor would make the re-run time out at
  once.
- Exercise the retry path for real (section 6). A budget that is wrong across retries passes every
  single-try test.

## 5. Errors, `soft_fail` and how the task ends

- On resume, a sensor turns **any `AirflowException`** into a skip when `soft_fail=True` (or
  `never_fail=True`). That includes `TaskDeferralError` from a trigger that raised, and the
  deferral timeout. Measured on 3.3.2: raising `AirflowException` in the resume method under
  `soft_fail` → `skipped`; raising a plain `RuntimeError` → `up_for_retry`, then `failed`.
- So when an error must fail the try and use the task's retries (an outage, an HTTP 5xx, a
  connection error), **the trigger yields an error event** (it does not raise). The resume method
  then raises an exception that is **not** an `AirflowException` subclass, for example the hook's
  own `class UpstreamApiError(Exception)`.
- Ending for good: `AirflowSensorTimeout` or `AirflowFailException` fail without retries, and
  `AirflowSkipException` skips. With `soft_fail`, raise the skip yourself when the budget runs out.
- **Ending the task from the trigger**: `yield TaskSuccessEvent(xcoms={"return_value": files})`
  (from `airflow.triggers.base`). `xcoms` is a `dict` of XCom key to JSON value, pushed key by key,
  and not pushed when the task goes to retry. The resume method is not called in a real
  deployment. **`airflow dags test` does not honour end events**: it calls the resume method with
  `event == "success"` (a string). So prefer a plain `TriggerEvent` plus `execute_complete` when you
  need local runs to be faithful.

## 6. Verifying a deferrable task locally

`airflow dags test <dag> <date>` (and `scripts/replay_runs.py`) runs the trigger **inline**. That
exercises `serialize()` → re-import → `run()` → the resume method, retries with `retry_delay`, and
XCom clearing between tries. It does **not**:

- enforce `defer(timeout=)` (a trigger that never fires blocks the test);
- restart the trigger mid-wait;
- pass `defer(kwargs=)`;
- honour `TaskSuccessEvent`;
- report event-loop stalls.

So add these checks:

1. Point the hook at a local stub or test endpoint and use small numbers (`timeout=6`,
   `poke_interval=1`, `retries=2`, `retry_delay=timedelta(seconds=1)`). Then run
   `airflow dags test`: success path, timeout path (time it: it must end near the budget, not
   after `retries × timeout`), error path (it must retry, also under `soft_fail`).
2. Simulate a restart: build the trigger from its `serialize()` output halfway through the wait
   and check that it still stops at the original deadline.
3. Run the loop-stall harness from section 3 against the stub with a slow (≥0.5 s) response.
4. Grep the trigger module for `requests`, `time.sleep`, `get_connection(`, `Variable.get` and sync
   hook calls.

If the project has no triggerer, say that the deferrable path was verified only in-process.
